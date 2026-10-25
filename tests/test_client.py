"""Client smoke test against a stub HTTP server (no model needed)."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CLIENT = Path(__file__).parents[1] / "scripts" / "hermes_tts_client.py"


class Stub(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self):
        Stub.received = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.end_headers()
        self.wfile.write(b"RIFF-stub")

    def log_message(self, format, *args):
        pass


def test_client_posts_text_and_writes_audio(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.handle_request, daemon=True).start()
    src, out = tmp_path / "in.txt", tmp_path / "out.wav"
    src.write_text("  Привет, мир.\n", encoding="utf-8")

    env = {"QWEN_TTS_URL": f"http://127.0.0.1:{server.server_port}"}
    subprocess.run(
        [sys.executable, str(CLIENT), str(src), str(out), "calm voice"],
        check=True,
        env=env,
        timeout=10,
    )
    server.server_close()

    assert out.read_bytes() == b"RIFF-stub"
    assert Stub.received == {
        "text": "Привет, мир.",
        "instruct": "calm voice",
        "language": "Russian",
        "format": "wav",
    }
