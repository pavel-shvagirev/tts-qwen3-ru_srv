#!/usr/bin/env python3
"""Hermes command-provider bridge: input text file -> output WAV or MP3."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Usage: hermes_tts_client.py INPUT_PATH OUTPUT_PATH VOICE_DESCRIPTION")

    input_path, output_path, instruct = sys.argv[1:4]
    text = Path(input_path).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("Input text is empty")
    if not instruct.strip():
        raise SystemExit("Voice description is empty: set tts.providers.<name>.voice")

    base_url = os.environ.get("QWEN_TTS_URL", "http://127.0.0.1:8031")
    timeout = int(os.environ.get("QWEN_TTS_CLIENT_TIMEOUT", "300"))
    payload = json.dumps(
        {
            "text": text,
            "instruct": instruct,
            "language": os.environ.get("QWEN_TTS_LANGUAGE", "Russian"),
            "format": "mp3" if output_path.lower().endswith(".mp3") else "wav",
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        base_url.rstrip("/") + "/tts",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"TTS server error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"TTS server unreachable at {base_url}: {exc.reason}") from exc

    if not audio:
        raise SystemExit("TTS server returned empty audio")
    Path(output_path).write_bytes(audio)


if __name__ == "__main__":
    main()
