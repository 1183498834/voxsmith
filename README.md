<div align="center">

<img src="assets/icon.svg" width="88" alt="VoxSmith icon">

# VoxSmith

**Give your text a voice — one that stays the same from the first sentence to the last.**

<a href="#english">English</a> · <a href="#中文">中文</a>

<sub>A <a href="https://github.com/1183498834">Codex</a> skill for turning scripts, articles, and notes into narrated MP3 audio.</sub>

</div>

---

## English

VoxSmith turns a text file into a narrated MP3. It exists because generated
narration is usually easy to produce and annoying to actually use, for three
reasons this skill takes seriously:

- **Engines break.** Microsoft's Edge neural voices started rejecting clients
  with `403` handshake errors, and hosted endpoints are unreachable on
  restricted networks. VoxSmith falls through a chain of four engines and tells
  you exactly why each one was skipped.
- **Levels jump.** The same sentence rendered by different engines measured
  −16, −19.5, and −20.7 LUFS. Played back to back, that is an obvious volume
  change. Every output is normalized to a single loudness target.
- **Voices drift.** Rendering five parts as five separate commands can silently
  land on five different engines. Batch mode locks one engine and one voice for
  the whole set.

### What it does

| Capability | Command | Why it matters |
| --- | --- | --- |
| Single file | `--input a.txt --output a.mp3` | The everyday case |
| Batch, one voice | `--inputs a.txt b.txt --outdir out` | Guarantees a single speaker |
| Join the batch | `--concat full.mp3` | Deliver a multi-part answer as one file |
| Audition voices | `preview_voices.py` | Compare candidates on one sample line |
| Text preflight | automatic | Flags `/`, `%`, `&` before they are misread |

### Requirements

- Python 3.9 or newer
- ffmpeg — obtained automatically through the `imageio-ffmpeg` wheel, so no
  system-wide install is needed
- curl — recommended; used for downloads because it aborts stalled transfers
  that a plain socket timeout does not catch
- Runs on Windows, macOS, and Linux

### Install

Clone into your Codex skills directory. On Linux and macOS:

```bash
git clone https://github.com/1183498834/voxsmith ~/.codex/skills/voxsmith
```

On Windows PowerShell:

```powershell
git clone https://github.com/1183498834/voxsmith "$env:USERPROFILE\.codex\skills\voxsmith"
```

Then just ask for a spoken version of a text, or invoke `$voxsmith` directly.

### Usage

```bash
# One file. The default --engine auto picks the first engine that works.
python scripts/tts.py --input script.txt --output intro.mp3

# A set that must sound like one speaker, delivered as a single file too.
python scripts/tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05

# Compare voices on one sample line, then open previews/index.html.
python scripts/preview_voices.py --voices en_US-ryan-high en_US-lessac-medium \
    en_GB-alan-medium --outdir previews

# See which voices are available.
python scripts/tts.py --list-voices
```

Useful knobs: `--rate 1.05` for a slightly slower read-aloud pace,
`--sentence-silence 0.45` for longer pauses between sentences, `--lufs -16` to
retarget loudness, and `--lufs 0` to leave the engine's own level alone.

### Engines

| Engine | Quality | Network | Notes |
| --- | --- | --- | --- |
| `edge` | Most natural | Required | Microsoft's online neural voices; currently answers `403` |
| `piper` | Natural, consistent | First run only | Local ONNX model, about 150 MB cached |
| `gtts` | Good | Required | Google Translate's speech endpoint |
| `sapi` | Robotic | None | Windows built-in, last resort |

`piper` is the recommended engine for anything you may regenerate later: it
pins a specific model file, so repeat runs are identical. Auto mode deliberately
does not trigger Piper's first-time download on its own — pass `--engine piper`
to accept it.

### Verification instead of listening

Every run prints a JSON report, which is what makes the pipeline checkable
without playing the audio back:

```json
{
  "ok": true,
  "engine": "piper",
  "voice": "en_US-ryan-high",
  "loudness": { "mean_db": -16.9, "peak_db": -1.9, "duration_s": 54.14 },
  "consistency": { "mean_db_spread": 0.3, "ok": true },
  "text_warnings": [],
  "attempts": [{ "engine": "edge", "ok": false, "reason": "... 403 ..." }]
}
```

`peak_db` at the true-peak ceiling confirms nothing clips, `duration_s` catches
truncated audio, and `consistency` catches a batch whose parts would be audible
as separate recordings.

### Layout

```text
voxsmith/
|-- SKILL.md                 Instructions Codex loads when the skill is used
|-- README.md                This file
|-- agents/openai.yaml       UI metadata
|-- assets/icon.svg          Logo
|-- references/engines.md    Engine trade-offs, voice ids, troubleshooting
`-- scripts/
    |-- tts.py               Synthesize, encode, normalize, report
    |-- setup_piper.py       Cache the Piper runtime and voice models
    `-- preview_voices.py    Render one sample per voice, build a listening page
```

### License

MIT — see [LICENSE](LICENSE).

---

## 中文

VoxSmith 把文本文件转成朗读音频（MP3）。做这个工具，是因为"能生成语音"和"生成出来的语音真的能用"之间隔着三个坑，而它们都被认真处理了：

- **引擎会失效。** 微软 Edge 的神经语音开始以 `403` 拒绝握手，而网络受限时托管接口根本连不上。VoxSmith 会在四个引擎之间依次降级，并且明确告诉你每个引擎为什么被跳过。
- **音量会跳。** 同一句话用不同引擎渲染，实测分别是 −16、−19.5、−20.7 LUFS，连着播放时音量变化非常明显。所有输出都会归一到同一个响度目标。
- **音色会飘。** 把五个段落跑五条命令，有可能悄悄落到五个不同引擎上。批量模式会为整组锁定同一个引擎和同一个音色。

### 功能一览

| 能力 | 命令 | 解决什么 |
| --- | --- | --- |
| 单文件 | `--input a.txt --output a.mp3` | 日常用法 |
| 批量、统一音色 | `--inputs a.txt b.txt --outdir out` | 保证只有一个人在说话 |
| 合并批量结果 | `--concat full.mp3` | 多段内容作为一个文件交付 |
| 音色试听 | `preview_voices.py` | 用同一句样音横向对比候选 |
| 文本预检 | 自动 | 在 `/`、`%`、`&` 被读错之前提示 |

### 环境要求

- Python 3.9 或更高版本
- ffmpeg —— 通过 `imageio-ffmpeg` 依赖包自动获取，不需要系统级安装
- curl —— 建议安装。下载通过 curl 完成，因为连接中途停滞时，普通 socket 超时不会触发，而 curl 会
- 支持 Windows、macOS、Linux

### 安装

克隆到 Codex 的 skills 目录。Linux / macOS：

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
# 单文件。默认 --engine auto 会依次尝试直到某个引擎可用。
python scripts/tts.py --input script.txt --output intro.mp3

# 一组需要音色一致的段落，同时合并成一个文件交付。
python scripts/tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05

# 用一句样音对比多个音色，然后打开 previews/index.html 试听。
python scripts/preview_voices.py --voices en_US-ryan-high en_US-lessac-medium \
    en_GB-alan-medium --outdir previews

# 查看当前可用的音色。
python scripts/tts.py --list-voices
```

常用参数：`--rate 1.05` 让语速稍慢一点便于跟读，`--sentence-silence 0.45` 加长句间停顿，`--lufs -16` 调整响度目标，`--lufs 0` 则完全保留引擎原始音量。

### 引擎对比

| 引擎 | 音质 | 需要联网 | 说明 |
| --- | --- | --- | --- |
| `edge` | 最自然 | 是 | 微软在线神经语音；目前返回 `403` |
| `piper` | 自然、稳定 | 仅首次 | 本地 ONNX 模型，约 150 MB 缓存 |
| `gtts` | 良好 | 是 | Google 翻译的语音接口 |
| `sapi` | 机械 | 否 | Windows 内置，最后兜底 |

如果之后可能重新生成同一段内容，建议用 `piper`：它固定指向某个模型文件，重复运行结果完全一致。auto 模式不会自动触发 Piper 的首次下载，需要时用 `--engine piper` 明确指定。

### 用报告代替试听

每次运行都会输出一份 JSON 报告，这让整条流水线不必靠耳朵就能校验：

```json
{
  "ok": true,
  "engine": "piper",
  "voice": "en_US-ryan-high",
  "loudness": { "mean_db": -16.9, "peak_db": -1.9, "duration_s": 54.14 },
  "consistency": { "mean_db_spread": 0.3, "ok": true },
  "text_warnings": [],
  "attempts": [{ "engine": "edge", "ok": false, "reason": "... 403 ..." }]
}
```

`peak_db` 贴着真峰值上限，说明没有削波；`duration_s` 能发现音频被截断；`consistency` 能发现一批文件之间会被听成"不同次录音"。

### 目录结构

```text
voxsmith/
|-- SKILL.md                 使用技能时 Codex 加载的指令
|-- README.md                本文件
|-- agents/openai.yaml       界面元数据
|-- assets/icon.svg          图标
|-- references/engines.md    引擎取舍、音色命名、故障排查
`-- scripts/
    |-- tts.py               合成、编码、响度归一、输出报告
    |-- setup_piper.py       缓存 Piper 运行时与音色模型
    `-- preview_voices.py    每个音色渲染一句样音并生成试听页
```

### 许可

MIT —— 详见 [LICENSE](LICENSE)。
