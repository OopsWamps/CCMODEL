# 本地语音识别字幕工作流

把视频 / 音频文件转写成 SRT 字幕文件。**全程本地运行，不上传任何数据**。

方案：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)（OpenAI Whisper 的 CTranslate2 加速版），CPU 即可运行，有 NVIDIA 显卡会快数倍。

## 文件

- `subtitle.py` —— 主脚本，已在本工作流中实际测试通过（中文视频 → 正确的 SRT）

## 一、安装（Windows 电脑）

1. 安装 Python 3.9+（https://www.python.org/downloads/ ，安装时勾选 **Add to PATH**）

2. 安装识别库（命令行执行）：

   ```bat
   pip install faster-whisper
   ```

3. 不需要单独安装 ffmpeg —— 脚本用 PyAV 直接解码 mp4/mkv/mov/mp3/wav/m4a/flac 等常见格式。

## 二、使用

```bat
:: 基本用法（自动检测语言，生成 视频.srt 和 视频.txt）
python subtitle.py 我的视频.mp4

:: 中文视频建议指定语言，识别更稳
python subtitle.py -l zh 我的视频.mp4

:: 批量处理整个文件夹
python subtitle.py -l zh 文件夹\*.mp4

:: 换模型（tiny / base / small / medium / large-v3）
python subtitle.py -m medium -l zh 我的视频.mp4

:: 指定输出目录
python subtitle.py -l zh -o D:\subs 我的视频.mp4
```

输出：

- `同名.srt` —— 字幕文件（带 BOM 的 UTF-8，可直接拖进剪映 / PR / PotPlayer 等）
- `同名.txt` —— 纯文本，方便复制整理

## 三、模型选择

| 模型 | 大小 | 建议 |
|------|------|------|
| tiny | 39M | 最快，中文质量差，只测流程用 |
| base | 74M | 轻量，中文勉强可用 |
| **small** | 244M | **默认推荐**，中文可用，CPU 也能接近实时 |
| medium | 769M | 中文质量好，速度较慢 |
| large-v3 | 1.5G | 质量最好，建议配显卡 |

首次运行会自动从 HuggingFace 下载所选模型并缓存（之后完全离线可用）。

**国内网络下载慢的话**，先设置镜像再运行：

```bat
set HF_ENDPOINT=https://hf-mirror.com
python subtitle.py -l zh 我的视频.mp4
```

## 四、性能参考

- 普通笔记本 CPU（int8 量化）：small 模型约 0.5~1 倍实时（1 小时视频约 30~60 分钟）
- NVIDIA 显卡：自动使用 CUDA，快 5~10 倍。需要装 CUDA 依赖：
  `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`（并把 pip 装好的 `nvidia\...\bin` 目录加入 PATH）

## 五、字幕进阶（可选）

- **压制硬字幕**（把字烧进画面）：
  `ffmpeg -i 视频.mp4 -vf "subtitles=视频.srt:force_style='FontSize=22'" 输出.mp4`
- **软字幕封装**（字幕可开关）：
  `ffmpeg -i 视频.mp4 -i 视频.srt -c copy -c:s mov_text 输出.mp4`
- 想要逐句润色，可把 `同名.txt` 喂给 AI 修改后，再手动替换 SRT 中的对应行。

## 六、常见问题

- **长视频出现重复/幻觉**：脚本已默认 `condition_on_previous_text=False` 并启用 VAD 静音过滤，一般可避免；仍出现可加大 VAD 参数或换 medium 模型。
- **双语/混杂口音**：不要传 `-l`，让其自动检测。
- **输出乱码**：脚本输出带 BOM 的 UTF-8，一般播放器和剪辑软件都能识别。