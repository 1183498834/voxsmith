# Engines, voices, and troubleshooting

Read this when the default engine does not fit: the voice must match a
previous file, the machine is offline or behind a restricted network, or
`tts.py` reported that every engine failed.

## Engine comparison

| Engine | Quality | Needs network | `--rate` | Notes |
| --- | --- | --- | --- | --- |
| `edge` | Most natural | Yes | Native | Microsoft's online neural voices |
| `piper` | Natural, consistent | First run only | Native | Local ONNX model, ~150 MB cache |
| `gtts` | Good | Yes | Via ffmpeg `atempo` | Google Translate endpoint |
| `sapi` | Clearly robotic | No | Via ffmpeg `atempo` | Windows built-in, last resort |

`--engine auto` tries `edge`, `piper`, `gtts`, `sapi` in that order and records
why each attempt was skipped or failed in the report's `attempts` field. Auto
runs deliberately skip `piper` unless its model is already cached, so that a
one-off request never turns into a surprise 150 MB download. Pass
`--engine piper` to accept that download and set it up.

## Choosing a voice for a series

What breaks a multi-part script is not quality but inconsistency: two engines
or two voices produce two speakers. When the user wants several files that
belong together — a talk split into sections, or a self-introduction plus a
follow-up answer — render them as one batch:

```bash
python tts.py --inputs intro.txt reasons.txt --outdir out \
    --concat interview_full.mp3 --engine piper --voice en_US-ryan-high --rate 1.05
```

The first item resolves an engine through the normal fallback chain, and its
engine and voice are then pinned for every remaining item. That pinning matters
precisely because the fallback is otherwise per-file: if one part happened to
reach a different engine than its neighbours, the voice would change mid-series.
Running separate commands with matching flags only works if every one of them
happens to pick the same engine.

`--concat` joins the rendered parts in `--inputs` order with a stream copy, so
the merged file is byte-for-byte the same audio as the parts and needs no
second normalization pass. Use it when the user wants one deliverable but may
still want to regenerate a single section.

Every part is loudness-normalized individually, and the report's `consistency`
block measures the resulting spread. Under about 1.0 dB is inaudible; a larger
spread usually means one part was mostly silence or otherwise degenerate.

Avoid `edge` and `gtts` for a series when the same text may be regenerated
later: both are hosted services whose voices can change under you. `piper`
pins a specific model file, so repeated runs stay identical.

## Auditioning voices

`preview_voices.py` renders one sample line across several candidates and
builds `index.html` with a player per voice, which is far cheaper than
generating a full script per candidate:

```bash
python preview_voices.py --engine piper \
    --voices en_US-ryan-high en_US-lessac-medium en_GB-alan-medium \
    --outdir previews
python preview_voices.py --engine edge \
    --voices en-US-AndrewMultilingualNeural en-US-AvaMultilingualNeural \
    --outdir previews
```

Each piper candidate is downloaded on first use, so audition `medium` voices
first and only promote the shortlist to `high`. A voice that does not exist
fails on its own card without stopping the rest of the run. Override the sample
with `--text` or `--text-file` when the choice depends on a particular kind of
content, such as numbers, technical terms, or the user's own name.

## Piper voice ids

The id encodes language, speaker, and quality tier: `<lang>-<name>-<quality>`,
for example `en_US-ryan-high`, `en_GB-alan-medium`, `de_DE-thorsten-medium`.

Quality tiers are `x_low`, `low`, `medium`, and `high`. `medium` is roughly
20 MB and sounds close to `high` at ~120 MB, so it is often the better default
when cache size or download time matters. The full catalog, including every
available language and speaker, is the `rhasspy/piper-voices` repository on
Hugging Face; browse it rather than guessing speaker names.

`--sentence-silence` is the main lever for a listenable read-aloud pace.
Defaults of `0.35` work for narration; `0.45` to `0.6` suits a script the
listener is expected to shadow or memorize.

## Troubleshooting

**`edge` returns 403 on the WebSocket handshake.** Microsoft periodically
tightens client validation, and when it does, every `edge-tts` version fails
with `WSServerHandshakeError: 403`. Do not spend time upgrading the package or
editing its bundled Chromium version string — neither helps. Treat 403 as
"engine unavailable" and switch engines.

**A local Codex proxy exists but has no speech endpoint.** `127.0.0.1:15721`
serves model chat completions only; `/v1/audio/speech` returns 404. Do not
route speech synthesis through it.

**Both hosted engines fail.** The machine is offline or the endpoints are
blocked. `piper` is the answer: it works with no network once cached, and
`setup_piper.py` already falls back to `hf-mirror.com` for the model download
and to a GitHub proxy for the runtime. After one successful setup run, set
`CODEX_TTS_HOME` to that cache directory to reuse it from anywhere.

**`sapi` on a non-Windows host** is unavailable by design; `System.Speech`
does not exist there. On Windows, `--list-voices` prints the installed names to
pass to `--voice`.

**Piper is bundled as a standalone binary, not a Python package.** It ships its
own ONNX runtime and espeak-ng, which is why it works on interpreters where
`torch`-based local TTS projects cannot install. Keep using the binary rather
than trying to pip install a neural TTS library.

## Why loudness normalization is on by default

Engines deliver wildly different levels — measured here at roughly -16 LUFS for
Piper, -19.5 for gTTS, and -20.7 for SAPI on the same text. `ffmpeg`'s
two-pass `loudnorm` brings each to the `--lufs` target (default -16, a
reasonable speech level) with a true-peak ceiling, so files from different
engines still play back at a consistent volume.

Every engine's output also tends to sit right at 0 dBFS with a handful of
clipped samples; the true-peak ceiling removes them. The report's `peak_db`
should read near the `--true-peak` value, and `input_lufs` shows what the raw
engine output measured before correction.

Use `--lufs 0` only when the raw engine level must be preserved.
