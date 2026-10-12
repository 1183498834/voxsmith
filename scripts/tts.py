#!/usr/bin/env python3
"""Synthesize speech from a text file and write a loudness-normalized MP3.

Engines, in the order ``--engine auto`` tries them:

* ``edge``  - Microsoft Edge's online neural voices (most natural, needs network)
* ``piper`` - local ONNX neural model (offline, stable voice identity)
* ``gtts``  - Google Translate's speech endpoint (needs network)
* ``sapi``  - Windows System.Speech (always available, noticeably robotic)

The script prints a single JSON object on stdout; progress and diagnostics go
to stderr. The JSON is the verification record: duration, measured loudness,
peak level, and any text characters known to be read incorrectly.

Usage:
    python tts.py --input script.txt --output out.mp3
    python tts.py --input script.txt --output out.mp3 --engine piper --voice en_US-ryan-high
    python tts.py --list-voices
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SETUP_PIPER = Path(__file__).resolve().parent / "setup_piper.py"

DEFAULT_VOICES = {
    "edge": "en-US-AndrewMultilingualNeural",
    "piper": "en_US-ryan-high",
    "sapi": None,
    "gtts": None,
}

DEFAULT_ORDER = ["edge", "piper", "gtts", "sapi"]

# Characters that TTS engines read incorrectly or drop. These produce the kind
# of defect no amount of audio verification catches by itself.
TEXT_TRAPS = {
    "/": "read literally or silently dropped - split the text into separate runs instead",
    "|": "usually dropped entirely",
    "&": "sometimes read as 'and', sometimes dropped",
    "%": "unreliable; write 'percent'",
    "#": "unreliable; write 'number'",
    "~": "usually dropped",
    "\\": "dropped",
    "<": "dropped",
    ">": "dropped",
}


class EngineUnavailable(RuntimeError):
    """Raised when an engine cannot be used in this environment."""


# --------------------------------------------------------------------------- #
# external tooling
# --------------------------------------------------------------------------- #


def ensure_module(module: str, package: str, allow_install: bool) -> None:
    """Import ``module``, installing ``package`` from PyPI if needed."""
    try:
        __import__(module)
        return
    except ImportError:
        pass
    if not allow_install:
        raise EngineUnavailable(f"{package} is not installed (--no-install given)")
    print(f"installing {package}", file=sys.stderr)
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", package],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode != 0:
        raise EngineUnavailable(f"pip install {package} failed: {proc.stderr.strip()[-300:]}")
    __import__(module)


def resolve_ffmpeg(explicit: str | None, allow_install: bool) -> str:
    """Locate an ffmpeg binary; ``imageio-ffmpeg`` ships one as a wheel."""
    if explicit:
        if not Path(explicit).is_file():
            raise SystemExit(f"ffmpeg not found at {explicit}")
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    if not allow_install:
        raise SystemExit("ffmpeg not found and --no-install given")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "imageio-ffmpeg"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SystemExit("could not obtain ffmpeg; install imageio-ffmpeg or ffmpeg") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(ffmpeg: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [ffmpeg, "-nostdin", *args],
        capture_output=True,
        text=True,
        errors="replace",
    )


def _json_object_containing(text: str, needle: str) -> dict | None:
    idx = text.find(needle)
    if idx < 0:
        return None
    start = text.rfind("{", 0, idx)
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def loudnorm_measure(ffmpeg: str, src: Path, lufs: float, tp: float, lra: float) -> dict | None:
    proc = run_ffmpeg(
        ffmpeg,
        [
            "-hide_banner",
            "-nostats",
            "-i",
            str(src),
            "-af",
            f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json",
            "-f",
            "null",
            "-",
        ],
    )
    return _json_object_containing(proc.stderr, '"input_i"')


def volume_stats(ffmpeg: str, src: Path) -> dict[str, float | None]:
    proc = run_ffmpeg(
        ffmpeg, ["-hide_banner", "-i", str(src), "-af", "volumedetect", "-f", "null", "-"]
    )
    stats: dict[str, float | None] = {"mean_db": None, "peak_db": None, "duration_s": None}
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            stats["mean_db"] = float(line.split("mean_volume:")[1].split("dB")[0])
        elif "max_volume:" in line:
            stats["peak_db"] = float(line.split("max_volume:")[1].split("dB")[0])
        elif line.strip().startswith("Duration:"):
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            parts = [float(p) for p in stamp.split(":")]
            stats["duration_s"] = round(parts[0] * 3600 + parts[1] * 60 + parts[2], 2)
    return stats


def encode_mp3(
    ffmpeg: str,
    src: Path,
    out: Path,
    *,
    lufs: float | None,
    tp: float,
    lra: float,
    atempo: float,
    bitrate: str,
    sample_rate: int,
    channels: int,
) -> dict:
    """Encode ``src`` to ``out`` as MP3, optionally loudness-normalizing it."""
    loudness: dict = {"normalized": False}
    filters: list[str] = []

    # atempo covers engines with no native rate control (gtts, sapi). ffmpeg
    # accepts 0.5-2.0 per instance, so chain copies beyond that range.
    post: list[str] = []
    remaining = atempo
    while remaining > 2.0:
        post.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        post.append("atempo=0.5")
        remaining /= 0.5
    if abs(remaining - 1.0) > 1e-3:
        post.append(f"atempo={remaining:.4f}")

    if lufs is not None:
        measured = loudnorm_measure(ffmpeg, src, lufs, tp, lra)
        if measured and measured.get("input_i") not in (None, "-inf"):
            loudness = {
                "normalized": True,
                "target_lufs": lufs,
                "input_lufs": float(measured["input_i"]),
                "input_tp_db": float(measured["input_tp"]),
                "mode": "linear",
            }
            filters.append(
                "loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={mi}:measured_LRA={mlra}"
                ":measured_TP={mtp}:measured_thresh={mth}:offset={off}:linear=true".format(
                    I=lufs,
                    TP=tp,
                    LRA=lra,
                    mi=measured["input_i"],
                    mlra=measured["input_lra"],
                    mtp=measured["input_tp"],
                    mth=measured["input_thresh"],
                    off=measured["target_offset"],
                )
            )

    def build(chain: list[str]) -> list[str]:
        cmd = ["-y", "-loglevel", "error", "-i", str(src)]
        if chain:
            cmd += ["-af", ",".join(chain)]
        return cmd + [
            "-codec:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            str(out),
        ]

    proc = run_ffmpeg(ffmpeg, build(post + filters))
    if proc.returncode != 0 and filters:
        # Loudnorm's linear mode can fail on very short or unusual input; a
        # single-pass encode is better than handing back no file at all.
        print("linear loudnorm failed, retrying in dynamic mode", file=sys.stderr)
        loudness["mode"] = "dynamic"
        proc = run_ffmpeg(ffmpeg, build(post + [f"loudnorm=I={lufs}:TP={tp}"]))
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg encode failed: {proc.stderr.strip()[-400:]}")

    loudness.update(volume_stats(ffmpeg, out))
    return loudness


# --------------------------------------------------------------------------- #
# engines
# --------------------------------------------------------------------------- #


def synth_edge(text: str, voice: str, rate: float, allow_install: bool, tmp: Path) -> Path:
    ensure_module("edge_tts", "edge-tts", allow_install)
    import asyncio

    import edge_tts

    out = tmp / "edge.mp3"
    percent = f"{round((rate - 1) * 100):+d}%"

    async def go() -> None:
        await edge_tts.Communicate(text, voice, rate=percent).save(str(out))

    try:
        asyncio.run(go())
    except Exception as exc:  # noqa: BLE001 - normalise the common failure
        if "403" in str(exc):
            raise EngineUnavailable(
                "Microsoft Edge TTS rejected the handshake with 403 (service-side "
                "client validation); use another engine"
            ) from exc
        raise EngineUnavailable(f"edge-tts failed: {type(exc).__name__}: {exc}") from exc
    if not out.is_file() or out.stat().st_size == 0:
        raise EngineUnavailable("edge-tts produced no audio")
    return out


def piper_paths(tools_dir: Path, voice: str, exe: str | None, model: str | None) -> tuple[Path, Path | None, Path]:
    if exe and model:
        return Path(exe), None, Path(model)
    cached = (tools_dir / "voices" / f"{voice}.onnx").is_file() and any(
        tools_dir.rglob("piper.exe" if sys.platform == "win32" else "piper")
    )
    if not cached:
        print(
            f"piper: first run for {voice}; downloading runtime and voice model "
            "(~150 MB, can take a few minutes on a slow link)",
            file=sys.stderr,
        )
    setup = subprocess.run(
        [sys.executable, str(SETUP_PIPER), "--voice", voice, "--tools-dir", str(tools_dir)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if setup.returncode != 0:
        raise EngineUnavailable(f"piper setup failed: {setup.stderr.strip()[-300:]}")
    info = _json_object_containing(setup.stdout, '"piper_exe"')
    if not info:
        raise EngineUnavailable("piper setup returned no path information")
    espeak = Path(info["espeak_data"]) if info.get("espeak_data") else None
    return Path(info["piper_exe"]), espeak, Path(info["model"])


def synth_piper(
    text: str,
    voice: str,
    rate: float,
    sentence_silence: float,
    tools_dir: Path,
    exe: str | None,
    model: str | None,
    tmp: Path,
) -> Path:
    exe_path, espeak, model_path = piper_paths(tools_dir, voice, exe, model)
    out = tmp / "piper.wav"
    cmd = [
        str(exe_path),
        "--model",
        str(model_path),
        "--output_file",
        str(out),
        "--length_scale",
        f"{1.0 / rate:.3f}",
        "--sentence_silence",
        f"{sentence_silence:.2f}",
        "--quiet",
    ]
    if espeak and espeak.is_dir():
        cmd += ["--espeak_data", str(espeak)]
    proc = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
    if proc.returncode != 0 or not out.is_file():
        raise EngineUnavailable(
            f"piper failed: {proc.stderr.decode('utf-8', 'replace').strip()[-300:]}"
        )
    return out


def synth_gtts(
    text: str, lang: str, tld: str, rate: float, allow_install: bool, tmp: Path
) -> Path:
    ensure_module("gtts", "gTTS", allow_install)
    from gtts import gTTS

    out = tmp / "gtts.mp3"
    try:
        # gTTS has no rate parameter; --rate is applied later via ffmpeg atempo.
        gTTS(text=text, lang=lang, slow=False, tld=tld).save(str(out))
    except Exception as exc:  # noqa: BLE001
        raise EngineUnavailable(f"gTTS failed: {type(exc).__name__}: {exc}") from exc
    if not out.is_file() or out.stat().st_size == 0:
        raise EngineUnavailable("gTTS produced no audio")
    return out


def list_sapi_voices() -> list[str]:
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer)"
        ".GetInstalledVoices()|%{$_.VoiceInfo.Name}"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def synth_sapi(text: str, voice: str | None, rate: float, tmp: Path) -> Path:
    if sys.platform != "win32":
        raise EngineUnavailable("sapi is only available on Windows")
    out = tmp / "sapi.wav"
    # System.Speech takes its text from a file rather than stdin so that the
    # encoding does not depend on the console code page.
    text_file = tmp / "sapi_text.txt"
    text_file.write_text(text, encoding="utf-8")
    # System.Speech Rate is an integer from -10 to 10, not a multiplier.
    sapi_rate = max(-10, min(10, round((rate - 1) * 10)))
    lines = [
        "Add-Type -AssemblyName System.Speech",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
    ]
    if voice:
        lines.append(f"$s.SelectVoice('{voice}')")
    lines += [
        f"$s.Rate = {sapi_rate}",
        f"$s.SetOutputToWaveFile('{out}')",
        f"$s.Speak((Get-Content -LiteralPath '{text_file}' -Raw -Encoding UTF8))",
        "$s.Dispose()",
    ]
    # -EncodedCommand sidesteps every quoting problem on Windows.
    encoded = ";".join(lines).encode("utf-16-le")
    import base64

    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(encoded).decode("ascii"),
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if not out.is_file() or out.stat().st_size == 0:
        raise EngineUnavailable(f"sapi produced no audio: {proc.stderr.strip()[-200:]}")
    return out


# --------------------------------------------------------------------------- #
# text inspection
# --------------------------------------------------------------------------- #


def inspect_text(text: str) -> list[str]:
    warnings = []
    for char, note in TEXT_TRAPS.items():
        count = text.count(char)
        if count:
            warnings.append(f"{count}x {char!r}: {note}")
    if re.search(r"\n\s*\n", text):
        warnings.append(
            "blank lines present: engine pauses vary, use --sentence-silence (piper) "
            "or split into separate files for deliberate paragraph breaks"
        )
    if not text.strip():
        warnings.append("text is empty")
    return warnings


def paragraph_break_safe(text: str) -> str:
    """Collapse runs of blank lines without rewriting the wording."""
    return re.sub(r"\n{2,}", "\n", text).strip()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def read_text(path: str, keep_paragraphs: bool) -> str:
    text = (
        sys.stdin.read()
        if path == "-"
        else Path(path).expanduser().read_text(encoding="utf-8")
    )
    if not keep_paragraphs:
        text = paragraph_break_safe(text)
    if not text.strip():
        raise SystemExit(f"input text is empty: {path}")
    return text


def pick_engine(
    text: str,
    order: list[str],
    args: argparse.Namespace,
    tools_dir: Path,
    tmp: Path,
    voice_hint: str | None = None,
) -> tuple[Path | None, str | None, str | None, list[dict]]:
    """Synthesize ``text`` with the first engine that works.

    Returns ``(audio_path, engine, voice, attempts)``, with ``audio_path`` set
    to None when every engine failed.
    """
    attempts: list[dict] = []
    for engine in order:
        voice = voice_hint or args.voice or DEFAULT_VOICES.get(engine)
        if engine == "piper" and args.engine == "auto" and not args.piper_model:
            # A first-time piper run downloads ~150 MB; do not surprise an auto
            # run with that. Explicit --engine piper still sets it up.
            if not (tools_dir / "voices" / f"{voice}.onnx").is_file():
                attempts.append({"engine": engine, "ok": False, "reason": "not cached"})
                continue
        try:
            print(f"engine {engine} ({voice or 'default'}): synthesizing", file=sys.stderr)
            if engine == "edge":
                audio = synth_edge(text, voice, args.rate, not args.no_install, tmp)
            elif engine == "piper":
                audio = synth_piper(
                    text,
                    voice,
                    args.rate,
                    args.sentence_silence,
                    tools_dir,
                    args.piper_exe,
                    args.piper_model,
                    tmp,
                )
            elif engine == "gtts":
                audio = synth_gtts(
                    text, args.lang, args.tld, args.rate, not args.no_install, tmp
                )
            else:
                audio = synth_sapi(text, voice, args.rate, tmp)
        except EngineUnavailable as exc:
            attempts.append({"engine": engine, "ok": False, "reason": str(exc)})
            print(f"  unavailable: {exc}", file=sys.stderr)
            continue
        attempts.append({"engine": engine, "ok": True})
        return audio, engine, voice, attempts
    return None, None, None, attempts


def render(
    text: str,
    output: Path,
    args: argparse.Namespace,
    ffmpeg: str,
    tools_dir: Path,
    tmp: Path,
    pinned: tuple[str, str | None] | None = None,
) -> dict:
    """Synthesize ``text`` into ``output`` and return a report dict."""
    if pinned:
        # Reuse the engine and voice already chosen for this batch, so that
        # every part is spoken by the same voice even if another engine is
        # available or a later item would otherwise fall back differently.
        order, voice_hint = [pinned[0]], pinned[1]
    else:
        order = DEFAULT_ORDER if args.engine == "auto" else [args.engine]
        voice_hint = None

    audio, engine, voice, attempts = pick_engine(
        text, order, args, tools_dir, tmp, voice_hint
    )
    if audio is None:
        return {"ok": False, "output": str(output), "attempts": attempts}

    output.parent.mkdir(parents=True, exist_ok=True)
    loudness = encode_mp3(
        ffmpeg,
        audio,
        output,
        lufs=None if args.lufs == 0 else args.lufs,
        tp=args.true_peak,
        lra=args.lra,
        # edge and piper take the rate natively; the others are stretched during
        # encoding so --rate behaves the same across engines.
        atempo=1.0 if engine in ("edge", "piper") else args.rate,
        bitrate=args.bitrate,
        sample_rate=args.sample_rate,
        channels=args.channels,
    )
    return {
        "ok": True,
        "output": str(output),
        "engine": engine,
        "voice": voice,
        "rate": args.rate,
        "size_bytes": output.stat().st_size,
        "bitrate": args.bitrate,
        "sample_rate": args.sample_rate,
        "loudness": loudness,
        "text_warnings": inspect_text(text),
        "attempts": attempts,
    }


def concat_parts(ffmpeg: str, parts: list[dict], target: Path, args: argparse.Namespace) -> dict:
    """Join already-rendered parts, in the given order, into one MP3."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        for part in parts:
            # The concat demuxer wants forward slashes and single-quoted paths.
            fh.write(f"file '{Path(part['output']).resolve().as_posix()}'\n")
        listfile = Path(fh.name)
    try:
        base = ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listfile)]
        proc = run_ffmpeg(ffmpeg, [*base, "-c", "copy", str(target)])
        if proc.returncode != 0:
            # A stream copy needs identical formats across parts; re-encode
            # rather than fail, since the parts came from this same run.
            proc = run_ffmpeg(
                ffmpeg,
                [
                    *base,
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    args.bitrate,
                    "-ar",
                    str(args.sample_rate),
                    "-ac",
                    str(args.channels),
                    str(target),
                ],
            )
        if proc.returncode != 0:
            raise SystemExit(f"concat failed: {proc.stderr.strip()[-300:]}")
    finally:
        listfile.unlink(missing_ok=True)
    return {
        "output": str(target),
        "size_bytes": target.stat().st_size,
        **volume_stats(ffmpeg, target),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize a text file to a loudness-normalized MP3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", help="UTF-8 text file, or - for stdin")
    parser.add_argument("--output", help="destination .mp3 path")
    parser.add_argument("--engine", default="auto", choices=["auto", *DEFAULT_ORDER])
    parser.add_argument("--voice", default=None, help="engine-specific voice id")
    parser.add_argument(
        "--rate",
        type=float,
        default=1.0,
        help="speaking rate multiplier, >1 is faster (default 1.0)",
    )
    parser.add_argument(
        "--sentence-silence",
        type=float,
        default=0.35,
        help="piper only: seconds of silence after each sentence (default 0.35)",
    )
    parser.add_argument("--lang", default="en", help="gtts only: language code")
    parser.add_argument("--tld", default="com", help="gtts only: accent domain, e.g. co.uk")
    parser.add_argument("--tools-dir", default=None, help="piper cache directory")
    parser.add_argument("--piper-exe", default=None, help="explicit piper binary")
    parser.add_argument("--piper-model", default=None, help="explicit piper .onnx model")
    parser.add_argument("--ffmpeg", default=None, help="explicit ffmpeg binary")
    parser.add_argument(
        "--lufs",
        type=float,
        default=-16.0,
        help="loudness target in LUFS; -16 suits speech (default), 0 disables",
    )
    parser.add_argument("--true-peak", type=float, default=-1.5, help="true peak ceiling in dBTP")
    parser.add_argument("--lra", type=float, default=11.0, help="loudness range target")
    parser.add_argument("--bitrate", default="192k", help="MP3 bitrate (default 192k)")
    parser.add_argument("--sample-rate", type=int, default=24000, help="output sample rate")
    parser.add_argument("--channels", type=int, default=1, help="1 = mono")
    parser.add_argument("--keep-paragraphs", action="store_true", help="keep blank lines in the text")
    parser.add_argument("--no-install", action="store_true", help="never pip install anything")
    parser.add_argument("--list-voices", action="store_true", help="show candidate voices and exit")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=None,
        help="batch mode: several text files rendered with one locked engine and voice",
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="batch mode: directory for the per-part MP3s (defaults to a temporary dir)",
    )
    parser.add_argument(
        "--concat",
        default=None,
        help="batch mode: also join every part, in --inputs order, into this MP3",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass

    if args.list_voices:
        print(json.dumps(list_voices(args), indent=2, ensure_ascii=False))
        return 0

    if args.input and args.inputs:
        parser.error("use either --input/--output or --inputs, not both")
    if not args.input and not args.inputs:
        parser.error("--input/--output or --inputs is required (or use --list-voices)")
    if args.input:
        if not args.output:
            parser.error("--output is required with --input")
        if args.outdir or args.concat:
            parser.error("--outdir and --concat only apply to --inputs")
    elif not args.outdir and not args.concat:
        parser.error("--inputs needs --outdir, --concat, or both")

    ffmpeg = resolve_ffmpeg(args.ffmpeg, not args.no_install)
    tools_dir = Path(args.tools_dir).expanduser() if args.tools_dir else _default_tools_dir()

    with tempfile.TemporaryDirectory(prefix="tts-") as tmpdir:
        tmp = Path(tmpdir)

        if args.input:
            text = read_text(args.input, args.keep_paragraphs)
            report = render(
                text,
                Path(args.output).expanduser(),
                args,
                ffmpeg,
                tools_dir,
                tmp,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report["ok"] else 1

        # Batch mode: lock the first successfully chosen engine and voice, then
        # reuse both for every remaining item so the whole set is one speaker.
        outdir = Path(args.outdir).expanduser() if args.outdir else tmp / "parts"
        outdir.mkdir(parents=True, exist_ok=True)
        concat_target = Path(args.concat).expanduser() if args.concat else None

        parts: list[dict] = []
        pinned: tuple[str, str | None] | None = None
        for position, src in enumerate(args.inputs, start=1):
            source = Path(src).expanduser()
            text = read_text(str(source), args.keep_paragraphs)
            report = render(
                text, outdir / f"{source.stem}.mp3", args, ffmpeg, tools_dir, tmp, pinned
            )
            if not report["ok"]:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "failed_input": str(source),
                            "completed": [p["output"] for p in parts],
                            "attempts": report["attempts"],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                raise SystemExit(f"batch stopped: could not synthesize {source}")
            if pinned is None:
                pinned = (report["engine"], report["voice"])
            report["input"] = str(source)
            print(
                f"  part {position}/{len(args.inputs)} -> {report['output']}",
                file=sys.stderr,
            )
            parts.append(report)

        levels = [
            p["loudness"]["mean_db"]
            for p in parts
            if p["loudness"].get("mean_db") is not None
        ]
        spread = round(max(levels) - min(levels), 2) if len(levels) > 1 else 0.0
        report = {
            "ok": True,
            "batch": True,
            "count": len(parts),
            "engine": pinned[0],
            "voice": pinned[1],
            "rate": args.rate,
            "consistency": {
                "mean_db_spread": spread,
                "ok": spread <= 1.0,
                "note": "parts above 1.0 dB apart will be audible as a level change",
            },
            "parts": [
                {
                    k: v
                    for k, v in p.items()
                    if k in ("input", "output", "size_bytes", "loudness", "text_warnings")
                }
                for p in parts
            ],
            "concat": concat_parts(ffmpeg, parts, concat_target, args)
            if concat_target
            else None,
        }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _default_tools_dir() -> Path:
    # VOXSMITH_HOME is the documented override. CODEX_TTS_HOME is honoured so
    # that caches created before the skill was renamed keep working.
    for variable in ("VOXSMITH_HOME", "CODEX_TTS_HOME"):
        override = os.environ.get(variable)
        if override:
            return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "voxsmith"
    return Path.home() / ".cache" / "voxsmith"


def list_voices(args: argparse.Namespace) -> dict:
    info: dict = {
        "defaults": {k: v for k, v in DEFAULT_VOICES.items() if v},
        "notes": {
            "piper": "voice id format <lang>-<name>-<quality>, e.g. en_US-ryan-high",
            "edge": "full Microsoft voice name; run `edge-tts --list-voices` for the catalog",
            "gtts": "uses --lang/--tld instead of --voice",
        },
    }
    if sys.platform == "win32":
        try:
            info["sapi"] = list_sapi_voices()
        except Exception as exc:  # noqa: BLE001
            info["sapi"] = f"unavailable: {exc}"
    return info


if __name__ == "__main__":
    raise SystemExit(main())
