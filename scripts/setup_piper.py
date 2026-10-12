#!/usr/bin/env python3
"""Download and cache the Piper TTS runtime plus a voice model.

Piper is a local ONNX neural TTS engine. It needs two things: a standalone
binary (which bundles espeak-ng for phonemization) and a voice model
(``.onnx`` + ``.onnx.json``).

Both downloads are large (runtime ~30 MB, high-quality voice ~120 MB), so this
script is idempotent: it skips anything already present. It prints one JSON
object with the resolved paths, which can be passed straight to ``tts.py``.

Usage:
    python setup_piper.py [--voice en_US-ryan-high] [--tools-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PIPER_RELEASE = "2023.11.14-2"

ASSETS = {
    "windows": "piper_windows_amd64.zip",
    "linux": "piper_linux_x86_64.tar.gz",
    "darwin": "piper_macos_x64.tar.gz",
}

PIPER_HOSTS = [
    "https://github.com/rhasspy/piper/releases/download",
    "https://ghproxy.net/https://github.com/rhasspy/piper/releases/download",
]

VOICE_HOSTS = [
    "https://huggingface.co",
    "https://hf-mirror.com",
]


def default_tools_dir() -> Path:
    override = os.environ.get("CODEX_TTS_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "codex-tts"
    return Path.home() / ".cache" / "codex-tts"


def platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def curl_path() -> str | None:
    return shutil.which("curl") or shutil.which("curl.exe")


def _curl(url: str, tmp: Path) -> None:
    """Fetch ``url`` with curl, aborting on a stalled transfer.

    A plain socket timeout does not fire when a proxy accepts a connection and
    then stops sending data, which is common on restricted networks. curl's
    rate limiter does: ``--speed-limit``/``--speed-time`` abort the transfer
    once it drops below 2 KB/s for 60 seconds, and ``--retry`` gives the
    connection a couple of chances before the caller tries another mirror.
    """
    proc = subprocess.run(
        [
            curl_path(),
            "-L",  # follow GitHub's redirect to the asset host
            "-f",  # treat HTTP errors as failures
            "-sS",
            "--retry", "3",
            "--retry-delay", "2",
            "--connect-timeout", "20",
            "--speed-limit", "2000",
            "--speed-time", "60",
            "--max-time", "1800",
            "-o", str(tmp),
            url,
        ],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode != 0:
        raise OSError(f"curl exit {proc.returncode}: {proc.stderr.strip()[-200:]}")


def _urllib(url: str, tmp: Path, timeout: int) -> None:
    """Fallback used when curl is not installed."""
    req = urllib.request.Request(url, headers={"User-Agent": "codex-tts/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        header = resp.headers.get("Content-Length")
        expected = int(header) if header and header.isdigit() else None
        written = 0
        with open(tmp, "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
                written += len(chunk)
                if expected is not None and written > expected:
                    break
        if expected is not None and written != expected:
            raise OSError(f"truncated: got {written} of {expected} bytes")


def download(urls: list[str], dest: Path, timeout: int = 60) -> None:
    """Download to ``dest``, trying each URL in order.

    A truncated archive is rejected rather than kept, because otherwise the
    failure surfaces much later as a confusing "not a zip file" error.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    failures: list[str] = []
    for url in urls:
        try:
            print(f"  fetching {url}", file=sys.stderr)
            if curl_path():
                _curl(url, tmp)
            else:
                _urllib(url, tmp, timeout)
            size = tmp.stat().st_size if tmp.exists() else 0
            if size == 0:
                raise OSError("empty response")
            tmp.replace(dest)
            print(f"  ok: {size / 1e6:.1f} MB", file=sys.stderr)
            return
        except Exception as exc:  # noqa: BLE001 - report and try the next mirror
            failures.append(f"{url} -> {type(exc).__name__}: {exc}")
            print(f"  failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    detail = "\n  ".join(failures)
    raise SystemExit(f"could not download {dest.name}; all mirrors failed:\n  {detail}")


def extract(archive: Path, root: Path) -> None:
    """Extract an archive, discarding it if it turns out to be unusable."""
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(root)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(root)
    except Exception as exc:  # noqa: BLE001
        archive.unlink(missing_ok=True)
        raise SystemExit(
            f"could not extract {archive.name} ({type(exc).__name__}: {exc}); "
            "the archive was removed - re-run to download it again"
        ) from exc


def detect_espeak_dir(root: Path) -> Path | None:
    for candidate in (root / "espeak-ng-data", root / "piper" / "espeak-ng-data"):
        if candidate.is_dir():
            return candidate
    return None


def ensure_runtime(tools_dir: Path) -> tuple[Path, Path | None]:
    """Return (piper executable, espeak data dir)."""
    key = platform_key()
    root = tools_dir / "piper"
    exe_name = "piper.exe" if key == "windows" else "piper"

    existing = sorted(root.rglob(exe_name)) if root.is_dir() else []
    if existing:
        exe = existing[0]
        return exe, detect_espeak_dir(exe.parent.parent) or detect_espeak_dir(root)

    asset = ASSETS[key]
    archive = tools_dir / asset
    urls = [f"{host}/{PIPER_RELEASE}/{asset}" for host in PIPER_HOSTS]
    print("runtime: downloading Piper", file=sys.stderr)
    download(urls, archive)

    root.mkdir(parents=True, exist_ok=True)
    extract(archive, root)

    found = sorted(root.rglob(exe_name))
    if not found:
        raise SystemExit(f"extracted {asset} but found no {exe_name}")
    exe = found[0]
    if key != "windows":
        exe.chmod(exe.stat().st_mode | 0o755)
    return exe, detect_espeak_dir(exe.parent.parent) or detect_espeak_dir(root)


def voice_urls(voice: str, suffix: str) -> list[str]:
    """Map a voice id such as ``en_GB-alan-medium`` to its model URLs."""
    try:
        lang_code, name, quality = voice.split("-")
    except ValueError:
        raise SystemExit(
            f"bad voice id {voice!r}; expected e.g. en_US-ryan-high or en_GB-alan-medium"
        ) from None
    if "_" not in lang_code:
        raise SystemExit(
            f"bad voice id {voice!r}; language must look like en_US, de_DE, zh_CN"
        )
    family = lang_code.split("_")[0]
    rel = f"{family}/{lang_code}/{name}/{quality}/{lang_code}-{name}-{quality}{suffix}"
    return [f"{host}/rhasspy/piper-voices/resolve/main/{rel}" for host in VOICE_HOSTS]


def ensure_voice(tools_dir: Path, voice: str) -> Path:
    model = tools_dir / "voices" / f"{voice}.onnx"
    config = tools_dir / "voices" / f"{voice}.onnx.json"
    if model.is_file() and config.is_file():
        return model
    print(f"voice: downloading {voice}", file=sys.stderr)
    download(voice_urls(voice, ".onnx"), model)
    download(voice_urls(voice, ".onnx.json"), config, timeout=60)
    return model


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache the Piper runtime and a voice model.")
    parser.add_argument("--voice", default="en_US-ryan-high", help="Piper voice id")
    parser.add_argument("--tools-dir", default=None, help="cache directory")
    parser.add_argument("--skip-runtime", action="store_true", help="only fetch the voice")
    args = parser.parse_args()

    tools_dir = Path(args.tools_dir).expanduser() if args.tools_dir else default_tools_dir()
    tools_dir.mkdir(parents=True, exist_ok=True)

    exe: Path | None = None
    espeak: Path | None = None
    if not args.skip_runtime:
        exe, espeak = ensure_runtime(tools_dir)
    model = ensure_voice(tools_dir, args.voice)

    info = {
        "tools_dir": str(tools_dir),
        "piper_exe": str(exe) if exe else None,
        "espeak_data": str(espeak) if espeak else None,
        "voice": args.voice,
        "model": str(model),
        "model_mb": round(model.stat().st_size / 1e6, 1),
    }
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - older interpreters
            pass
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
