#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地字幕助手：选择文件/目录，多选媒体文件并批量生成 SRT/TXT。"""

import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk


def app_icon_path(suffix: str = ".png") -> Path | None:
    """定位应用图标：打包后在 _MEIPASS 内，源码运行在项目 assets/ 目录。"""
    if hasattr(sys, "_MEIPASS"):
        path = Path(sys._MEIPASS) / f"icon{suffix}"
    else:
        path = Path(__file__).resolve().parent.parent / "assets" / f"icon{suffix}"
    return path if path.exists() else None


def apply_window_icon(window: tk.Tk) -> None:
    """设置窗口与任务栏图标。Windows 下先注册独立 AppUserModelID，
    让任务栏把本程序当作独立应用而不是 Python 解释器。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ccmodel.subtitle.assistant")
        except Exception:
            pass
    ico = app_icon_path(".ico")
    if ico:
        try:
            window.iconbitmap(str(ico))
            return
        except tk.TclError:
            pass
    png = app_icon_path(".png")
    if png:
        window._icon_img = tk.PhotoImage(file=str(png))  # 持有引用，防止被回收
        window.iconphoto(True, window._icon_img)

MEDIA_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts",
    ".mp3", ".wav", ".m4a", ".flac", ".aac", ".wma", ".ogg", ".opus",
}

# 配色：浅色系，青色主色与 assets/icon.png 呼应
BG = "#f4f7fb"           # 窗口底色（浅蓝白）
SURFACE = "#ffffff"      # 卡片 / 输入框 / 按钮白
RAISED = "#eef4fa"       # hover 浅蓝
BORDER = "#d9e2ec"       # 浅灰蓝边框
LOG_BG = "#0f1923"       # 日志区保留深色终端感
LOG_FG = "#a8c0d0"
TEXT = "#1d2b3a"         # 主文字（深蓝）
MUTED = "#5f7385"        # 次要文字
ACCENT = "#00c2e0"       # 主按钮青
ACCENT_HOVER = "#2fd0ea"
ACCENT_PRESSED = "#00a8c4"
ACCENT_TEXT = "#0286a8"  # 浅底上的青色文字
ACCENT_DARK = "#04252e"  # 青底上的深色文字
DISABLED_BG = "#f0f4f8"
DISABLED_FG = "#9aa9b7"
FONT_UI = "Microsoft YaHei UI"
FONT_LOG = "Consolas"


def fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def choose_output_base(media: Path, output_dir: str, reserved: set[Path]) -> Path:
    parent = Path(output_dir) if output_dir else media.parent
    parent.mkdir(parents=True, exist_ok=True)
    base = parent / media.stem
    candidate = base
    n = 2
    while candidate.with_name(candidate.name + ".srt").exists() or candidate.with_name(candidate.name + ".txt").exists() or candidate in reserved:
        candidate = parent / f"{media.stem}_{n}"
        n += 1
    reserved.add(candidate)
    return candidate


class SubtitleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("本地字幕助手")
        self.geometry("1200x880")
        self.minsize(1050, 800)
        self.files: list[Path] = []
        self.events: queue.Queue = queue.Queue()
        self.running = False

        self.recursive_var = tk.BooleanVar(value=True)
        self.model_var = tk.StringVar(value="small")
        self.lang_var = tk.StringVar(value="中文 (zh)")
        self.output_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="请选择视频/音频文件，或扫描一个目录。")

        self._setup_style()
        self._build_ui()
        apply_window_icon(self)
        self.after(120, self._poll_events)

    @staticmethod
    def _pill(fill: str, outline: str | None, master: tk.Tk) -> ImageTk.PhotoImage:
        """生成圆角按钮九宫格贴图：4x 超采样绘制后缩小，边缘平滑。"""
        w, h, r, ss = 64, 38, 12, 4
        img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            (0, 0, w * ss - 1, h * ss - 1), radius=r * ss,
            fill=fill, outline=outline, width=ss if outline else 0,
        )
        img = img.resize((w, h), Image.LANCZOS)
        return ImageTk.PhotoImage(img, master=master)

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, font=(FONT_UI, 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", foreground=MUTED, font=(FONT_UI, 9))
        style.configure("Header.TLabel", font=(FONT_UI, 16, "bold"))
        style.configure("Sub.TLabel", foreground=MUTED, font=(FONT_UI, 9))

        # 圆角按钮：ttk 不支持原生圆角，用 PIL 九宫格贴图注册为图片元素。
        # 状态顺序：disabled / pressed 优先匹配，避免 hover 态遮住按下态。
        self._btn_images = {
            "sec": self._pill(SURFACE, BORDER, self),
            "sec_h": self._pill(RAISED, "#c3d2e0", self),
            "sec_p": self._pill("#e2ebf3", "#b4c6d6", self),
            "sec_d": self._pill(DISABLED_BG, "#e3e9ef", self),
            "acc": self._pill(ACCENT, None, self),
            "acc_h": self._pill(ACCENT_HOVER, None, self),
            "acc_p": self._pill(ACCENT_PRESSED, None, self),
            "acc_d": self._pill(DISABLED_BG, None, self),
        }
        style.element_create(
            "Sec.btn", "image", self._btn_images["sec"],
            ("disabled", self._btn_images["sec_d"]),
            ("pressed", self._btn_images["sec_p"]),
            ("active", self._btn_images["sec_h"]),
            border=(16, 16, 16, 16), padding=(14, 0), sticky="nsew",
        )
        style.layout("TButton", [("Sec.btn", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})])
        style.configure("TButton", background=BG, foreground=TEXT,
                        borderwidth=0, focusthickness=0, font=(FONT_UI, 10))
        style.map("TButton", foreground=[("disabled", DISABLED_FG)])

        style.element_create(
            "Acc.btn", "image", self._btn_images["acc"],
            ("disabled", self._btn_images["acc_d"]),
            ("pressed", self._btn_images["acc_p"]),
            ("active", self._btn_images["acc_h"]),
            border=(16, 16, 16, 16), padding=(18, 0), sticky="nsew",
        )
        style.layout("Accent.TButton", [("Acc.btn", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})])
        style.configure("Accent.TButton", background=BG, foreground=ACCENT_DARK,
                        borderwidth=0, focusthickness=0, font=(FONT_UI, 10, "bold"))
        style.map("Accent.TButton", foreground=[("disabled", DISABLED_FG)])

        # 输入框 / 下拉框：白底、浅边框
        style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                        insertcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, borderwidth=1, padding=6)
        style.configure("TCombobox", fieldbackground=SURFACE, background=RAISED,
                        foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, borderwidth=1, padding=6)
        style.map("TCombobox",
                  fieldbackground=[("readonly", SURFACE)],
                  foreground=[("readonly", TEXT)],
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        self.option_add("*TCombobox*Listbox.background", SURFACE)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", ACCENT_DARK)
        self.option_add("*TCombobox*Listbox.font", (FONT_UI, 10))

        style.configure("TCheckbutton", background=BG, foreground=TEXT,
                        focuscolor=BG, bordercolor=BORDER)
        style.map("TCheckbutton",
                  background=[("active", BG)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", SURFACE)],
                  bordercolor=[("selected", ACCENT)])

        style.configure("TLabelframe", background=BG, bordercolor=BORDER,
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT_TEXT,
                        font=(FONT_UI, 10, "bold"))

        style.configure("Horizontal.TProgressbar", background=ACCENT,
                        troughcolor="#e4ebf2", borderwidth=0, thickness=8)

    def _build_ui(self):
        root = ttk.Frame(self, padding=(16, 12, 16, 12))
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="本地字幕助手", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="  本地运行 · 数据不出本机", style="Sub.TLabel").pack(side="left", pady=(6, 0))

        controls = ttk.Frame(root)
        controls.pack(fill="x")
        self.add_btn = ttk.Button(controls, text="添加文件（可多选）…", command=self.add_files)
        self.add_btn.pack(side="left", padx=(0, 8))
        self.scan_btn = ttk.Button(controls, text="选择目录并扫描…", command=self.scan_folder)
        self.scan_btn.pack(side="left")
        ttk.Checkbutton(controls, text="包括子文件夹", variable=self.recursive_var).pack(side="left", padx=(12, 0))
        ttk.Button(controls, text="移除选中", command=self.remove_selected).pack(side="right")
        ttk.Button(controls, text="清空列表", command=self.clear_files).pack(side="right", padx=(0, 8))

        ttk.Label(root, text="文件列表（Ctrl / Shift 多选）", style="Muted.TLabel").pack(anchor="w", pady=(10, 4))
        list_frame = ttk.Frame(root)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED, exportselection=False, height=6,
            bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground=ACCENT_DARK,
            relief="flat", highlightthickness=0, activestyle="none",
            font=(FONT_UI, 10),
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)

        opts = ttk.LabelFrame(root, text=" 转写设置 ", padding=(12, 8))
        opts.pack(fill="x", pady=(10, 0))
        ttk.Label(opts, text="模型：").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.model_var, state="readonly", width=14,
                     values=("tiny", "base", "small", "medium", "large-v3")).grid(row=0, column=1, sticky="w", padx=(6, 20))
        ttk.Label(opts, text="语言：").grid(row=0, column=2, sticky="w")
        ttk.Combobox(opts, textvariable=self.lang_var, state="readonly", width=16,
                     values=("中文 (zh)", "自动检测", "English (en)")).grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(opts, text="small 推荐；模型首次使用时下载，之后离线可用；CPU 模式，无需 CUDA。",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        outrow = ttk.Frame(root)
        outrow.pack(fill="x", pady=(10, 0))
        ttk.Label(outrow, text="输出目录（留空则与每个源文件放在一起）：").pack(side="left")
        ttk.Entry(outrow, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(outrow, text="浏览…", command=self.choose_output).pack(side="right")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(12, 0))
        self.start_btn = ttk.Button(bottom, text="开始批量转写", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        ttk.Label(root, text="运行日志", style="Muted.TLabel").pack(anchor="w", pady=(8, 4))
        self.log = tk.Text(
            root, height=5, wrap="word", state="disabled",
            bg=LOG_BG, fg=LOG_FG, insertbackground=TEXT,
            relief="flat", highlightthickness=0,
            selectbackground=RAISED, selectforeground=TEXT,
            font=(FONT_LOG, 9), padx=10, pady=8,
        )
        self.log.pack(fill="both", expand=False)

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _add_paths(self, paths):
        existing = {p.resolve() for p in self.files}
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.is_file() and p.suffix.lower() in MEDIA_EXTS:
                resolved = p.resolve()
                if resolved not in existing:
                    self.files.append(p)
                    self.listbox.insert("end", str(p))
                    existing.add(resolved)
                    added += 1
        self.status_var.set(f"共 {len(self.files)} 个文件，新增 {added} 个。")

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择视频/音频文件（可多选）",
            filetypes=[("媒体文件", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.mp3 *.wav *.m4a *.flac *.aac *.wma *.ogg *.opus"), ("所有文件", "*.*")],
        )
        if paths:
            self._add_paths(paths)

    def scan_folder(self):
        folder = filedialog.askdirectory(title="选择视频/音频目录")
        if not folder:
            return
        root = Path(folder)
        iterator = root.rglob("*") if self.recursive_var.get() else root.glob("*")
        paths = sorted((p for p in iterator if p.is_file() and p.suffix.lower() in MEDIA_EXTS), key=lambda p: str(p).lower())
        self._add_paths(paths)
        self._log(f"目录扫描完成：找到 {len(paths)} 个媒体文件：{root}")

    def remove_selected(self):
        indices = list(self.listbox.curselection())
        for i in reversed(indices):
            self.listbox.delete(i)
            del self.files[i]
        self.status_var.set(f"剩余 {len(self.files)} 个文件。")

    def clear_files(self):
        if self.running:
            return
        self.files.clear()
        self.listbox.delete(0, "end")
        self.status_var.set("文件列表已清空。")

    def choose_output(self):
        folder = filedialog.askdirectory(title="选择字幕输出目录")
        if folder:
            self.output_var.set(folder)

    def start(self):
        if self.running:
            return
        selected = list(self.listbox.curselection())
        if not selected:
            messagebox.showinfo("提示", "请先在列表中选择一个或多个文件。\n可按住 Ctrl / Shift 多选。")
            return
        files = [self.files[i] for i in selected]
        self.running = True
        self.start_btn.configure(state="disabled")
        self.add_btn.configure(state="disabled")
        self.scan_btn.configure(state="disabled")
        self.progress.configure(maximum=len(files), value=0)
        lang_label = self.lang_var.get()
        language = {"中文 (zh)": "zh", "English (en)": "en", "自动检测": None}.get(lang_label)
        model_size = self.model_var.get()
        output_dir = self.output_var.get().strip()
        self.status_var.set("正在启动…")
        thread = threading.Thread(target=self._worker, args=(files, model_size, language, output_dir), daemon=True)
        thread.start()

    def _worker(self, files, model_size, language, output_dir):
        try:
            from faster_whisper import WhisperModel
            self.events.put(("log", f"正在加载 {model_size} 模型（CPU / int8）…首次使用可能需要下载模型。"))
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
        except Exception as exc:
            self.events.put(("fatal", f"模型加载失败：{exc}\n\n请确认已运行：python -m pip install faster-whisper"))
            return

        reserved: set[Path] = set()
        succeeded = 0
        failed = 0
        for index, media in enumerate(files, start=1):
            self.events.put(("status", f"处理中 {index}/{len(files)}：{media.name}"))
            self.events.put(("log", f"\n[{index}/{len(files)}] 转写：{media}"))
            try:
                segments, info = model.transcribe(
                    str(media),
                    language=language,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                    beam_size=5,
                    condition_on_previous_text=False,
                    initial_prompt="以下是普通话的句子。" if language == "zh" else None,
                )
                collected = [(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]
                if not collected:
                    raise RuntimeError("没有识别到语音。请确认文件有音轨，且音频清晰。")
                base = choose_output_base(media, output_dir, reserved)
                with open(base.with_name(base.name + ".srt"), "w", encoding="utf-8-sig") as f:
                    for n, (start, end, text) in enumerate(collected, start=1):
                        f.write(f"{n}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n\n")
                with open(base.with_name(base.name + ".txt"), "w", encoding="utf-8") as f:
                    f.write("\n".join(text for _, _, text in collected))
                self.events.put(("log", f"完成：{base.with_name(base.name + '.srt')}（{len(collected)} 条字幕；检测语言 {info.language}）"))
                succeeded += 1
            except Exception as exc:
                failed += 1
                message = str(exc)
                if "tuple index out of range" in message or "Stream map" in message:
                    message += "；可能没有可读取的音轨，可先用 FFmpeg 提取 WAV 后再转写。"
                self.events.put(("log", f"失败：{media.name}\n  {message}"))
            self.events.put(("progress", index))

        self.events.put(("done", f"批量任务结束：成功 {succeeded} 个，失败 {failed} 个。"))

    def _poll_events(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == "log":
                    self._log(message)
                elif kind == "status":
                    self.status_var.set(message)
                elif kind == "progress":
                    self.progress.configure(value=message)
                elif kind == "fatal":
                    self._log(message)
                    messagebox.showerror("无法开始转写", message)
                    self._finish()
                elif kind == "done":
                    self._log(message)
                    self.status_var.set(message)
                    self._finish()
                    messagebox.showinfo("完成", message)
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def _finish(self):
        self.running = False
        self.start_btn.configure(state="normal")
        self.add_btn.configure(state="normal")
        self.scan_btn.configure(state="normal")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    SubtitleApp().mainloop()
