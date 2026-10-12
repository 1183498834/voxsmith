#!/usr/bin/env python3
"""Render the same sample line in several voices and build a listening page.

Comparing voices by generating full scripts is wasteful. This renders one
short sample per candidate into a single folder and writes an ``index.html``
with an audio player per voice, so the whole shortlist can be auditioned in a
browser in order.

Usage:
    python preview_voices.py --engine piper \
        --voices en_US-ryan-high en_US-lessac-medium en_GB-alan-medium \
        --outdir previews

    python preview_voices.py --engine edge \
        --voices en-US-AndrewMultilingualNeural en-US-AvaMultilingualNeural \
        --outdir previews

Each piper voice has to be downloaded on first use (20 MB for ``medium``,
~120 MB for ``high``), so prefer auditioning a few ``medium`` candidates
before committing to a ``high`` one.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TTS = HERE / "tts.py"

DEFAULT_SAMPLE = (
    "Good morning, and thank you for the opportunity. "
    "This is how this voice reads a short script aloud."
)


def render_voice(voice: str, args: argparse.Namespace, outdir: Path, text: str) -> dict:
    command = [
        sys.executable,
        str(TTS),
        "--input",
        "-",
        "--output",
        str(outdir / f"{voice}.mp3"),
        "--engine",
        args.engine,
        "--voice",
        voice,
        "--rate",
        str(args.rate),
        "--sentence-silence",
        str(args.sentence_silence),
    ]
    for flag, value in (
        ("--tools-dir", args.tools_dir),
        ("--ffmpeg", args.ffmpeg),
        ("--lang", args.lang),
        ("--tld", args.tld),
    ):
        if value:
            command += [flag, str(value)]
    if args.no_install:
        command.append("--no-install")

    print(f"[{voice}] synthesizing", file=sys.stderr)
    # No text=True here: subprocess treats an `errors=` argument as a request
    # for text mode, and writing bytes into the resulting TextIOWrapper kills
    # the writer thread and deadlocks the child on stdin. Decode instead.
    proc = subprocess.run(command, input=text.encode("utf-8"), capture_output=True)
    raw = proc.stdout.decode("utf-8", "replace")
    start = raw.find("{")
    if proc.returncode != 0 or start < 0:
        return {
            "voice": voice,
            "ok": False,
            "reason": (proc.stderr.decode("utf-8", "replace").strip() or raw.strip())[-300:],
        }
    try:
        report = json.loads(raw[start:])
    except json.JSONDecodeError:
        return {"voice": voice, "ok": False, "reason": "unparsable report from tts.py"}
    if not report.get("ok"):
        attempts = report.get("attempts") or []
        reason = attempts[-1].get("reason") if attempts else "engine unavailable"
        return {"voice": voice, "ok": False, "reason": reason}
    return {
        "voice": voice,
        "ok": True,
        "output": report["output"],
        "duration_s": report["loudness"].get("duration_s"),
        "size_bytes": report["size_bytes"],
    }


def build_index(args: argparse.Namespace, results: list[dict], text: str) -> str:
    cards = []
    for item in results:
        name = html.escape(item["voice"])
        if item["ok"]:
            duration = item.get("duration_s")
            meta = f"{duration:.1f}s" if isinstance(duration, (int, float)) else ""
            body = (
                f'<audio controls preload="none" src="{html.escape(Path(item["output"]).name)}">'
                "</audio>"
            )
        else:
            meta = "unavailable"
            body = f'<p class="err">{html.escape(str(item["reason"]))}</p>'
        cards.append(
            f'<li class="card"><div class="row"><span class="name">{name}</span>'
            f'<span class="meta">{html.escape(meta)}</span></div>{body}</li>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoxSmith &middot; voice previews</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px; background: #14161a; color: #e8eaed;
    font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  main {{ max-width: 720px; margin: 0 auto; }}
  h1 {{ margin: 0 0 4px; font-size: 26px; letter-spacing: -0.01em; }}
  .sub {{ margin: 0 0 28px; color: #9aa0a6; font-size: 14px; }}
  .sample {{
    margin: 0 0 28px; padding: 14px 16px; border-left: 3px solid #6c8cff;
    background: #1b1e24; border-radius: 0 8px 8px 0; color: #c8ccd2; font-size: 15px;
  }}
  ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
  .card {{ background: #1b1e24; border: 1px solid #262a31; border-radius: 12px; padding: 16px; }}
  .row {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 10px; }}
  .name {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; }}
  .meta {{ color: #9aa0a6; font-size: 13px; white-space: nowrap; }}
  .err {{ margin: 0; color: #ff8a80; font-size: 13px; }}
  audio {{ width: 100%; height: 36px; }}
</style>
</head>
<body>
<main>
  <h1>Voice previews</h1>
  <p class="sub">engine: {html.escape(args.engine)} &middot; {len(results)} candidate(s)</p>
  <p class="sample">{html.escape(text)}</p>
  <ul>
    {"".join(cards)}
  </ul>
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render one sample line in several voices and build an index page."
    )
    parser.add_argument("--voices", nargs="+", required=True, help="voice ids to compare")
    parser.add_argument(
        "--engine", default="piper", choices=["edge", "piper", "gtts", "sapi"]
    )
    parser.add_argument("--outdir", default="voice-previews", help="output directory")
    parser.add_argument("--text", default=None, help="sample text (overrides the default)")
    parser.add_argument("--text-file", default=None, help="read the sample from this file")
    parser.add_argument("--rate", type=float, default=1.0, help="speaking rate multiplier")
    parser.add_argument("--sentence-silence", type=float, default=0.35, help="piper pause")
    parser.add_argument("--lang", default=None, help="gtts only: language code")
    parser.add_argument("--tld", default=None, help="gtts only: accent domain")
    parser.add_argument("--tools-dir", default=None, help="piper cache directory")
    parser.add_argument("--ffmpeg", default=None, help="explicit ffmpeg binary")
    parser.add_argument("--no-install", action="store_true", help="never pip install")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
    else:
        text = (args.text or DEFAULT_SAMPLE).strip()
    if not text:
        raise SystemExit("sample text is empty")

    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    results = [render_voice(voice, args, outdir, text) for voice in args.voices]

    index = outdir / "index.html"
    index.write_text(build_index(args, results, text), encoding="utf-8")

    summary = {
        "ok": all(r["ok"] for r in results),
        "engine": args.engine,
        "index": str(index),
        "succeeded": sum(1 for r in results if r["ok"]),
        "failed": [r["voice"] for r in results if not r["ok"]],
        "voices": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
