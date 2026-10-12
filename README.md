<div align="center">

<img src="assets/icon.svg" width="96" alt="VoxSmith icon">

# VoxSmith

**A general-purpose text-to-speech skill: turn any written text into narrated MP3 audio, in one consistent voice and at one consistent level.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

<a href="#english">English</a> · <a href="#中文">中文</a>

</div>

---

## English

### What it is

VoxSmith is a **general-purpose** Codex skill for text-to-speech. It makes no
assumptions about the subject matter, the language, or how the audio will be
used. Hand it any UTF-8 text file and it returns a narration-ready MP3: it
selects a speech engine that works on your machine, renders the audio,
normalizes the level, and reports what it produced.

Being general-purpose, it suits both one-off conversions and scripts you intend
to keep and reuse — a spoken self-introduction, the sections of a talk, a
reading of an article, study notes, or a draft voiceover.

### What it does

| Capability | Description |
| --- | --- |
| **Works with any content** | No domain-specific assumptions: technical papers, fiction, teaching material, announcements, and personal scripts are all treated the same |
| **Narrate a script** | One command turns a text file into an MP3, with voice, pace, and pause length under your control |
| **Keep a set in one voice** | Batch mode locks a single engine and voice for every part, so a multi-section recording sounds like one speaker |
| **Join a set into one file** | An optional concat step merges the parts, in order, into a single deliverable |
| **Match levels across files** | Every output is normalized to the same loudness target, so files play back at a consistent volume |
| **Audition voices first** | Render one sample line across several candidate voices into a page with a player per voice |
| **Catch unreadable text** | Symbols that speech engines read incorrectly are flagged before anything is generated |
| **Verify without listening** | Each run prints a JSON report with duration, loudness, peak level, and the outcome of each engine |
| **Run offline** | The local neural engine needs no network after its one-time setup |

### Where it applies

Because the skill is general-purpose, it fits wherever written text should be
heard. Common examples:

- **Interviews and applications.** Turn a prepared self-introduction or a
  research summary into audio you can rehearse against, and hear how it lands
  before you say it out loud to anyone.
- **Language learning.** Produce listening material from your own texts, and use
  the pace control for shadowing practice.
- **Study and revision.** Convert notes, abstracts, and long documents into
  audio for commutes and walks.
- **Content production.** Generate narration for videos, slide decks, and
  podcast segments from a written script.
- **Accessibility.** Give written material a spoken form without a recording
  setup.
- **Voice prototyping.** Draft announcement or IVR lines quickly, and compare
  voices before committing to one.

### Requirements

- Python 3.9 or newer
- ffmpeg, obtained automatically through the `imageio-ffmpeg` package, so no
  system-wide install is needed
- curl, recommended for downloads
- Windows, macOS, or Linux

Voice availability depends on the engine. The local Piper engine covers dozens
of languages through its voice catalogue, the Google engine takes a language
code, and the Edge neural voices span a wide range of locales.

### Installation

Clone the repository into your Codex skills directory.

Linux and macOS:

```bash
git clone https://github.com/1183498834/voxsmith ~/.codex/skills/voxsmith
```

Windows PowerShell:

```powershell
git clone https://github.com/1183498834/voxsmith "$env:USERPROFILE\.codex\skills\voxsmith"
```

Then ask for a spoken version of a text, or invoke the skill directly as
`$voxsmith`.

### Usage

```bash
# Narrate one file. The default --engine auto picks the first engine that works.
python scripts/tts.py --input script.txt --output intro.mp3

# Narrate a set in one voice, and also deliver it as a single file.
python scripts/tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05

# Compare voices on one sample line, then open previews/index.html.
python scripts/preview_voices.py --voices en_US-ryan-high en_US-lessac-medium \
    en_GB-alan-medium --outdir previews

# List the voices available in this environment.
python scripts/tts.py --list-voices
```

Common options:

| Option | Purpose |
| --- | --- |
| `--engine` | Choose an engine explicitly, or leave it on `auto` |
| `--voice` | Select a voice for that engine |
| `--rate 1.05` | Read slightly slower, which suits scripts spoken aloud |
| `--sentence-silence 0.45` | Lengthen the pause between sentences |
| `--lufs -16` | Set the loudness target in LUFS; `--lufs 0` leaves the level untouched |
| `--concat full.mp3` | Join a batch into one file, in `--inputs` order |
| `--bitrate`, `--sample-rate` | Control the output format |

### Engines

| Engine | Voice quality | Network | Typical use |
| --- | --- | --- | --- |
| `edge` | Most natural | Required | Online neural voices, the default first choice |
| `piper` | Natural and stable | First run only | Local neural model; best for anything you will regenerate |
| `gtts` | Good | Required | Google's speech endpoint, broad language coverage |
| `sapi` | Robotic | None | Windows built-in voice, always available |

When `--engine auto` is in effect, VoxSmith works down that list and uses the
first engine it can reach, recording the outcome of each attempt in the report.
If you name an engine explicitly, that one is used, and the first-run model
download for Piper is never started without your asking for it.

### Output and report

Every run prints a JSON report, so a batch can be checked without opening the
audio:

```json
{
  "ok": true,
  "engine": "piper",
  "voice": "en_US-ryan-high",
  "loudness": { "mean_db": -16.9, "peak_db": -1.9, "duration_s": 54.14 },
  "consistency": { "mean_db_spread": 0.3, "ok": true },
  "text_warnings": [],
  "attempts": [{ "engine": "edge", "ok": true }]
}
```

- `loudness.duration_s` is the length of the finished audio.
- `loudness.peak_db` confirms nothing is clipped.
- `consistency.mean_db_spread` reports how closely a batch's parts match in
  level, which is what keeps a joined set from sounding like separate
  recordings.
- `text_warnings` lists characters that would be read incorrectly.
- `attempts` records which engine was used.

### Project structure

```text
voxsmith/
|-- SKILL.md                 Instructions Codex loads when the skill is used
|-- README.md                This file
|-- agents/openai.yaml       UI metadata
|-- assets/icon.svg          Logo
|-- references/engines.md    Engine trade-offs, voice ids, operating notes
`-- scripts/
    |-- tts.py               Synthesize, encode, normalize, report
    |-- setup_piper.py       Cache the Piper runtime and voice models
    `-- preview_voices.py    Render one sample per voice and build a listening page
```

### License

MIT — see [LICENSE](LICENSE).

---

## 中文

**通用型文本转语音技能：把任意文本转成朗读 MP3，音色统一、音量统一。**

### 这是什么

VoxSmith 是一个**通用型**的文本转语音 Codex 技能。它不限定题材、语言，也不预设音频会用在什么场合。给它任意一个 UTF-8 文本文件，它会返回一个可以直接使用的朗读 MP3：自动挑选在本机可用的语音引擎、合成音频、统一响度，并输出一份说明本次生成结果的报告。

正因为是通用技能，它既适合临时转换一次，也适合需要反复使用的稿子——面试自我介绍、演讲稿的各个章节、文章朗读、学习笔记，以及配音草稿。

### 能做什么

| 能力 | 说明 |
| --- | --- |
| **任意内容都能用** | 没有领域假设：技术论文、小说、教学材料、播报文案、个人稿件一视同仁 |
| **朗读单篇文稿** | 一条命令把文本文件转成 MP3，音色、语速、停顿长度都可控 |
| **整组统一音色** | 批量模式为所有段落锁定同一个引擎和同一个音色，多章节录音听起来像同一个人的声音 |
| **多段合并成一个文件** | 可选的合并步骤按顺序把各段拼成单一成品 |
| **跨文件统一音量** | 所有输出归一到同一个响度目标，连续播放时音量保持一致 |
| **先试听再决定** | 用同一句样音渲染多个候选音色，并生成每张卡片带播放器的试听页 |
| **提前发现读不对的字符** | 在生成之前提示会被语音引擎读错的符号 |
| **不听也能校验** | 每次运行输出 JSON 报告，包含时长、响度、峰值，以及各引擎的执行结果 |
| **可离线运行** | 本地神经语音引擎在完成一次性配置后无需联网 |

### 适用场景

由于这是一个通用技能，凡是"文字需要被听见"的地方都适用。常见的例子包括：

- **面试与申请。** 把准备好的自我介绍或研究简介转成音频，反复跟读练习，在真正说给别人听之前先听自己的表达效果。
- **语言学习。** 用自己的文本生成听力材料，配合语速控制做影子跟读。
- **学习与复习。** 把笔记、摘要和长篇文档转成音频，在通勤和散步时听。
- **内容生产。** 由文字稿生成视频、幻灯片和播客片段的旁白。
- **无障碍。** 不需要录音设备，就能为书面材料提供语音版本。
- **语音原型。** 快速产出播报或 IVR 文案草稿，并在定稿前对比不同音色。

### 环境要求

- Python 3.9 或更高版本
- ffmpeg，通过 `imageio-ffmpeg` 依赖包自动获取，无需系统级安装
- curl，建议安装，用于下载
- Windows、macOS 或 Linux

可用音色取决于引擎。本地 Piper 引擎通过其音色库覆盖数十种语言，Google 引擎接受语言代码，Edge 神经语音覆盖广泛的地区口音。

### 安装

把仓库克隆到 Codex 的 skills 目录。

Linux 和 macOS：

```bash
git clone https://github.com/1183498834/voxsmith ~/.codex/skills/voxsmith
```

Windows PowerShell：

```powershell
git clone https://github.com/1183498834/voxsmith "$env:USERPROFILE\.codex\skills\voxsmith"
```

之后直接说"把这段文字转成语音"，或者显式调用 `$voxsmith`。

### 用法

```bash
# 朗读单个文件。默认 --engine auto 会挑选第一个可用的引擎。
python scripts/tts.py --input script.txt --output intro.mp3

# 用统一音色朗读一组文稿，同时合并成一个文件交付。
python scripts/tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05

# 用一句样音对比多个音色，然后打开 previews/index.html 试听。
python scripts/preview_voices.py --voices en_US-ryan-high en_US-lessac-medium \
    en_GB-alan-medium --outdir previews

# 查看当前环境中可用的音色。
python scripts/tts.py --list-voices
```

常用参数：

| 参数 | 用途 |
| --- | --- |
| `--engine` | 明确指定引擎，或保持 `auto` |
| `--voice` | 为该引擎选择音色 |
| `--rate 1.05` | 语速稍慢，适合需要朗读出来的稿子 |
| `--sentence-silence 0.45` | 加长句间停顿 |
| `--lufs -16` | 以 LUFS 为单位设定响度目标；`--lufs 0` 则保留原始音量 |
| `--concat full.mp3` | 按 `--inputs` 顺序把批量结果合并成一个文件 |
| `--bitrate`、`--sample-rate` | 控制输出格式 |

### 引擎对比

| 引擎 | 音质 | 需要联网 | 典型用途 |
| --- | --- | --- | --- |
| `edge` | 最自然 | 是 | 在线神经语音，auto 模式的首选 |
| `piper` | 自然、稳定 | 仅首次 | 本地神经模型，适合需要反复生成的内容 |
| `gtts` | 良好 | 是 | Google 语音接口，语言覆盖广 |
| `sapi` | 机械 | 否 | Windows 内置音色，始终可用 |

当 `--engine auto` 生效时，VoxSmith 会按上表顺序依次尝试，使用第一个可用的引擎，并在报告中记录每次尝试的结果。如果你明确指定了引擎，则直接使用该引擎；Piper 的首次模型下载也不会在没有明确指定的情况下自动触发。

### 输出与报告

每次运行都会打印一份 JSON 报告，批量任务不必打开音频就能核对：

```json
{
  "ok": true,
  "engine": "piper",
  "voice": "en_US-ryan-high",
  "loudness": { "mean_db": -16.9, "peak_db": -1.9, "duration_s": 54.14 },
  "consistency": { "mean_db_spread": 0.3, "ok": true },
  "text_warnings": [],
  "attempts": [{ "engine": "edge", "ok": true }]
}
```

- `loudness.duration_s` 是成品音频的时长。
- `loudness.peak_db` 用于确认没有削波。
- `consistency.mean_db_spread` 反映一批音频各段之间的音量差异，这正是拼接后的成品听起来像"同一次录音"的关键。
- `text_warnings` 列出会被读错的字符。
- `attempts` 记录实际使用的是哪个引擎。

### 目录结构

```text
voxsmith/
|-- SKILL.md                 使用技能时 Codex 加载的指令
|-- README.md                本文件
|-- agents/openai.yaml       界面元数据
|-- assets/icon.svg          图标
|-- references/engines.md    引擎取舍、音色命名、操作说明
`-- scripts/
    |-- tts.py               合成、编码、响度归一、输出报告
    |-- setup_piper.py       缓存 Piper 运行时与音色模型
    `-- preview_voices.py    每个音色渲染一句样音并生成试听页
```

### 许可

MIT —— 详见 [LICENSE](LICENSE)。
