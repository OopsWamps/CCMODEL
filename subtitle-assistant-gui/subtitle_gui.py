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
        self.geometry("900x680")
        self.minsize(720, 520)
        self.files: list[Path] = []
        self.events: queue.Queue = queue.Queue()
        self.running = False

        self.recursive_var = tk.BooleanVar(value=True)
        self.model_var = tk.StringVar(value="small")
        self.lang_var = tk.StringVar(value="中文 (zh)")
        self.output_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="请选择视频/音频文件，或扫描一个目录。")

        self._build_ui()
        apply_window_icon(self)
        self.after(120, self._poll_events)

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        controls = ttk.Frame(root)
        controls.pack(fill="x")
        self.add_btn = ttk.Button(controls, text="添加文件（可多选）…", command=self.add_files)
        self.add_btn.pack(side="left", padx=(0, 6))
        self.scan_btn = ttk.Button(controls, text="选择目录并扫描…", command=self.scan_folder)
        self.scan_btn.pack(side="left", padx=6)
        ttk.Checkbutton(controls, text="包括子文件夹", variable=self.recursive_var).pack(side="left", padx=8)
        ttk.Button(controls, text="移除选中", command=self.remove_selected).pack(side="right", padx=(6, 0))
        ttk.Button(controls, text="清空列表", command=self.clear_files).pack(side="right", padx=6)

        ttk.Label(root, text="文件列表（可用 Ctrl / Shift 多选）：").pack(anchor="w", pady=(12, 4))
        list_frame = ttk.Frame(root)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, exportselection=False, height=12)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scroll.set)

        opts = ttk.LabelFrame(root, text="转写设置", padding=10)
        opts.pack(fill="x", pady=(12, 0))
        ttk.Label(opts, text="模型：").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opts, textvariable=self.model_var, state="readonly", width=14,
                     values=("tiny", "base", "small", "medium", "large-v3")).grid(row=0, column=1, sticky="w", padx=(4, 18))
        ttk.Label(opts, text="语言：").grid(row=0, column=2, sticky="w")
        ttk.Combobox(opts, textvariable=self.lang_var, state="readonly", width=16,
                     values=("中文 (zh)", "自动检测", "English (en)")).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(opts, text="small 推荐；模型首次使用时会下载，之后可离线使用。默认 CPU 模式，不依赖 CUDA。", foreground="#555").grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(8, 2))

        outrow = ttk.Frame(root)
        outrow.pack(fill="x", pady=(10, 0))
        ttk.Label(outrow, text="输出目录（留空则与每个源文件放在一起）：").pack(side="left")
        ttk.Entry(outrow, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(outrow, text="浏览…", command=self.choose_output).pack(side="right")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(12, 0))
        self.start_btn = ttk.Button(bottom, text="开始批量转写", command=self.start)
        self.start_btn.pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        ttk.Label(bottom, textvariable=self.status_var, width=28).pack(side="right")

        ttk.Label(root, text="运行日志：").pack(anchor="w", pady=(10, 4))
        self.log = tk.Text(root, height=8, wrap="word", state="disabled")
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
    SubtitleApp().mainloop()
