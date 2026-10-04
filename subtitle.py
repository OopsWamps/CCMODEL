#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地语音识别字幕工作流
用法:
  python3 subtitle.py 视频.mp4                  # 单个文件, 输出 视频.srt + 视频.txt
  python3 subtitle.py a.mp4 b.mp3 c.mov         # 批量处理
  python3 subtitle.py -m small 视频.mp4         # 指定模型 (tiny/base/small/medium/large-v3)
  python3 subtitle.py -l zh 视频.mp4            # 指定语言 (不指定则自动检测, 中文推荐 -l zh)
  python3 subtitle.py -o 输出目录 视频.mp4      # 指定输出目录
依赖: pip install faster-whisper   (首次运行会自动下载所选模型, 之后离线可用)
"""

import argparse
import os
import sys
import time
from pathlib import Path

from faster_whisper import WhisperModel

MODEL_SIZES = {
    "tiny":      {"params": "39M",  "vram": "~1GB", "note": "速度最快, 英文可用, 中文质量差"},
    "base":      {"params": "74M",  "vram": "~1GB", "note": "轻量, 中文勉强可用"},
    "small":     {"params": "244M", "vram": "~2GB", "note": "推荐的性价比之选, 中文可用"},
    "medium":    {"params": "769M", "vram": "~5GB", "note": "中文质量好, 速度较慢"},
    "large-v3":  {"params": "1.5G", "vram": "~10GB","note": "质量最好, 需较强机器"},
}

def fmt_ts(seconds: float) -> str:
    """秒 -> SRT 时间戳 00:00:01,500"""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def pick_device() -> str:
    return "cpu"

def transcribe_file(model: WhisperModel, media: Path, out_dir: Path,
                    language: str | None, vad: bool) -> Path:
    print(f"\n[1/2] 转写: {media.name}")
    t0 = time.time()
    segments, info = model.transcribe(
        str(media),
        language=language,          # None = 自动检测; 指定 "zh" 更稳
        vad_filter=vad,             # VAD 过滤静音段, 提速且减少幻觉
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
        condition_on_previous_text=False,  # 避免长音频的重复/幻觉连锁
        initial_prompt="以下是普通话的句子。" if language == "zh" else None,
    )

    segs = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            segs.append((seg.start, seg.end, text))
            print(f"  [{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}] {text}")

    elapsed = time.time() - t0
    dur = getattr(info, "duration", 0) or 0
    if dur:
        print(f"  音频时长 {dur:.0f}s, 耗时 {elapsed:.0f}s (实时率 {elapsed/dur:.2f}x)")

    out_srt = out_dir / (media.stem + ".srt")
    out_txt = out_dir / (media.stem + ".txt")

    with open(out_srt, "w", encoding="utf-8-sig") as f:  # 带BOM, 方便PR/剪映/播放器识别
        for i, (start, end, text) in enumerate(segs, 1):
            f.write(f"{i}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n\n")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(t for _, _, t in segs))

    print(f"[2/2] 已生成: {out_srt}  ({len(segs)} 条字幕)")
    print(f"           {out_txt}")
    return out_srt

def main():
    ap = argparse.ArgumentParser(description="本地视频/音频 -> SRT 字幕")
    ap.add_argument("inputs", nargs="+", help="媒体文件 (mp4/mkv/mov/mp3/wav/m4a/flac...)")
    ap.add_argument("-m", "--model", default="small", choices=MODEL_SIZES.keys(),
                    help="模型大小, 默认 small")
    ap.add_argument("-l", "--language", default=None,
                    help="语言代码: zh=中文, en=英文...; 不填自动检测")
    ap.add_argument("-o", "--out-dir", default=None, help="输出目录, 默认与源文件相同")
    ap.add_argument("--no-vad", action="store_true", help="关闭 VAD 静音过滤")
    args = ap.parse_args()

    device = pick_device()
    compute = "float16" if device == "cuda" else "int8"
    print(f"模型: {args.model} | 设备: {device} ({compute})")
    print(f"说明: {MODEL_SIZES[args.model]['note']}")

    model = WhisperModel(args.model, device=device, compute_type=compute)

    for inp in args.inputs:
        media = Path(inp)
        if not media.exists():
            print(f"跳过(不存在): {inp}", file=sys.stderr)
            continue
        out_dir = Path(args.out_dir) if args.out_dir else media.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        transcribe_file(model, media, out_dir, args.language, not args.no_vad)

if __name__ == "__main__":
    main()