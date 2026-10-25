#!/usr/bin/env python3
"""Local HTTP service for Qwen3-TTS VoiceDesign on Apple Silicon."""

import asyncio
import io
import logging
import os
import socket
import stat
import subprocess
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal, NoReturn

# Never download the model: Hub access in this process is cache-only. Only the
# checksum check (a subprocess with its own environment) talks to the Hub.
os.environ["HF_HUB_OFFLINE"] = "1"

MODEL_ID = os.environ.get(
    "QWEN_TTS_MODEL",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
)
HOST = os.environ.get("QWEN_TTS_HOST", "127.0.0.1")
PORT = int(os.environ.get("QWEN_TTS_PORT", "8031"))
# Generation cap in codec tokens. mlx-audio defaults to 2048 (~164 s at 12.5 Hz),
# which silently truncates long inputs.
MAX_TOKENS = int(os.environ.get("QWEN_TTS_MAX_TOKENS", "4096"))
# Offline mode: if this file exists next to the server, checksums are not checked.
SKIP_VERIFY_MARKER = Path(__file__).resolve().parent / "SKIP_MODEL_VERIFY"


def setup_logging() -> None:
    """Log to a size-rotated file when QWEN_TTS_LOG_DIR is set, else to stderr."""
    log_dir = os.environ.get("QWEN_TTS_LOG_DIR")
    max_bytes = int(os.environ.get("QWEN_TTS_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            os.path.join(log_dir, "server.log"),
            maxBytes=max_bytes,
            backupCount=int(os.environ.get("QWEN_TTS_LOG_BACKUPS", "3")),
            encoding="utf-8",
        )
        # Raw stderr (native crashes, library warnings) is a launchd file
        # without rotation: truncate it on start once it outgrows the limit.
        stderr_stat = os.fstat(2)
        if stat.S_ISREG(stderr_stat.st_mode) and stderr_stat.st_size > max_bytes:
            os.ftruncate(2, 0)
            os.lseek(2, 0, os.SEEK_SET)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Uncaught errors, including failed imports below, go to the same log.
    sys.excepthook = lambda *exc: logging.critical("Uncaught exception", exc_info=exc)


def fatal(message: str) -> NoReturn:
    logging.critical(message)
    raise SystemExit(1)


def check_port() -> None:
    """Fail before the slow model load if the address is taken."""
    family, kind, _, _, address = socket.getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)[0]
    with socket.socket(family, kind) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # as uvicorn does
        try:
            sock.bind(address)
        except OSError as exc:
            fatal(f"Cannot listen on {HOST}:{PORT}: {exc}. Free the port or set QWEN_TTS_PORT.")


def verify_model() -> None:
    """Check the cached model against Hub checksums; never download it."""
    if os.path.isdir(MODEL_ID):
        logging.info("Model is a local directory, checksum verification skipped: %s", MODEL_ID)
        return
    if SKIP_VERIFY_MARKER.exists():
        logging.warning("Checksum verification skipped, %s exists", SKIP_VERIFY_MARKER)
        require_cached_model()
        return
    command = [sys.executable, "-m", "huggingface_hub.cli.hf", "cache", "verify", MODEL_ID]
    command.append("--fail-on-missing-files")
    try:
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "HF_HUB_OFFLINE": "0"},
        )
    except subprocess.TimeoutExpired:
        fatal(f"Model check for {MODEL_ID} did not finish in 600 s.")
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        fatal(
            f"Model check failed for {MODEL_ID}: missing, corrupted or Hub unreachable."
            f" Download it manually, see README.\n{output}"
        )
    logging.info("Model checksums verified: %s", MODEL_ID)


def require_cached_model() -> None:
    """Fail clearly if the model is not in the local cache (offline mode)."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        snapshot_download(MODEL_ID)  # cache lookup only: HF_HUB_OFFLINE=1
    except LocalEntryNotFoundError:
        fatal(f"Model {MODEL_ID} is not in the local cache. Download it, see README.")


# Configure logging before the heavy imports so their failures are recorded.
setup_logging()
if __name__ == "__main__":
    check_port()
    verify_model()

import mlx.core as mx  # noqa: E402
import numpy as np  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Response  # noqa: E402
from mlx_audio.audio_io import write as audio_write  # noqa: E402
from mlx_audio.tts.utils import load_model  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

model = None
generation_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global model
    model = load_model(MODEL_ID)
    yield


app = FastAPI(title="Local Qwen3-TTS", version="1.1.0", lifespan=lifespan)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    instruct: str = Field(min_length=1, max_length=3000)
    language: str = "Russian"
    seed: int = 42
    temperature: float = 0.6
    top_p: float = 0.9
    format: Literal["wav", "mp3"] = "wav"


@app.get("/health")
def health(response: Response):
    if model is None:
        response.status_code = 503
    return {"status": "ok" if model is not None else "loading", "model": MODEL_ID}


def synthesize_audio(req: SpeechRequest) -> bytes:
    mx.random.seed(req.seed)
    chunks = [
        np.array(result.audio.astype(mx.float32))
        for result in model.generate_voice_design(
            text=req.text,
            language=req.language,
            instruct=req.instruct,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=MAX_TOKENS,
        )
    ]
    if not chunks:
        raise RuntimeError("Model returned no audio")
    buf = io.BytesIO()
    audio_write(buf, np.concatenate(chunks), model.sample_rate, format=req.format)
    return buf.getvalue()


@app.post("/tts")
async def synthesize(req: SpeechRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    async with generation_lock:
        try:
            audio = await asyncio.to_thread(synthesize_audio, req)
        except Exception as exc:
            logging.exception("Synthesis failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    media_type = "audio/mpeg" if req.format == "mp3" else "audio/wav"
    return Response(content=audio, media_type=media_type)


if __name__ == "__main__":
    # log_config=None: uvicorn loggers propagate to the root handler above.
    uvicorn.run(app, host=HOST, port=PORT, log_config=None)
