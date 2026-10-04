# 本地字幕助手（Windows 桌面版）

一个本地运行的图形界面，用于从视频/音频批量生成 `.srt` 字幕和 `.txt` 文本。默认使用 CPU/int8，不依赖 NVIDIA CUDA/cuBLAS，不会上传媒体文件。

## 启动

确保已安装 Python 和 faster-whisper。首次安装：

```powershell
python -m pip install faster-whisper
```

将 `subtitle_gui.py` 放在任意文件夹，打开 PowerShell 进入该文件夹后运行：

```powershell
python .\subtitle_gui.py
```

如果双击 `.py` 文件可启动 Python 窗口，也可以直接双击运行。

## 使用步骤

1. 点击 **选择目录并扫描…**，选视频/音频目录；默认会递归扫描子文件夹，可取消“包括子文件夹”。也可以点 **添加文件（可多选）…**。
2. 在文件列表中选择要处理的文件：按住 **Ctrl** 逐个多选，按住 **Shift** 连选一段。
3. 选择模型和语言。普通话建议 `small` + `中文 (zh)`；中英混杂或不确定时选“自动检测”。
4. 输出目录留空时，每个 `.srt` / `.txt` 会放在对应源文件旁边；选了输出目录时则统一输出到该目录。
5. 点击 **开始批量转写**。模型首次运行时会下载，下载后可离线使用；窗口日志会显示进度、成功/失败和输出路径。

支持格式：mp4、mkv、mov、avi、webm、m4v、ts，以及 mp3、wav、m4a、flac、aac、wma、ogg、opus。

## 常见问题

- **缺少 Tkinter**：Windows 官方 Python 安装程序通常包含 Tk/Tcl；如果启动时报 `No module named tkinter`，重新运行 Python 安装程序，选择 Modify 并启用 Tcl/Tk and IDLE。
- **提示找不到音轨 / PyAV 解码失败**：先确认视频本身有声音。可安装 FFmpeg 后提取音频：

  ```powershell
  ffmpeg -i "视频.mp4" -map 0:a:0 -vn -ac 1 -ar 16000 -c:a pcm_s16le "extracted.wav"
  ```

  再把 `extracted.wav` 添加到助手转写。
- **CPU 速度较慢**：可先用 `small`；`tiny` 更快但中文识别质量较差。该版固定用 CPU，避免缺少 CUDA/cuBLAS 导致启动失败；如需 GPU 版，可以在确认 CUDA 依赖后再扩展。
- **模型下载慢**：Windows PowerShell 可在启动前临时设置 Hugging Face 镜像：

  ```powershell
  $env:HF_ENDPOINT = "https://hf-mirror.com"
  python .\subtitle_gui.py
  ```
