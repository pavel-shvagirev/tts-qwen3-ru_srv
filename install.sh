#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
DEFAULT_HOME="$HOME/Library/Application Support/hermes-qwen3-tts"
INSTALL_DIR=${1:-$DEFAULT_HOME}
PYTHON=${PYTHON:-python3}
LABEL="local.tts-ru.hermes-qwen3-tts"

# Server settings baked into the LaunchAgent; override at install time, e.g.
#   QWEN_TTS_PORT=8032 ./install.sh
QWEN_TTS_HOST=${QWEN_TTS_HOST:-127.0.0.1}
QWEN_TTS_PORT=${QWEN_TTS_PORT:-8031}
QWEN_TTS_MODEL=${QWEN_TTS_MODEL:-mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16}
QWEN_TTS_MAX_TOKENS=${QWEN_TTS_MAX_TOKENS:-4096}
QWEN_TTS_LOG_MAX_BYTES=${QWEN_TTS_LOG_MAX_BYTES:-5242880}
QWEN_TTS_LOG_BACKUPS=${QWEN_TTS_LOG_BACKUPS:-3}
LAUNCH_PATH=${LAUNCH_PATH:-/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin}

case "$(uname -s)" in
  Darwin) ;;
  *) echo "Error: this package requires macOS and Apple Silicon (MLX)." >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64) ;;
  *) echo "Error: MLX requires Apple Silicon (arm64)." >&2; exit 1 ;;
esac
command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "Error: $PYTHON not found. Install Python (3.12 preferred)." >&2
  exit 1
}
# macOS ships python3 3.9 with the Command Line Tools; mlx-audio needs 3.10+.
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || {
  echo "Error: $PYTHON is $("$PYTHON" -V 2>&1); Python 3.10+ is required." >&2
  echo "  Install one (brew install python@3.12) and rerun with PYTHON=python3.12 $0" >&2
  exit 1
}

# Values go into plist XML unescaped.
for value in "$INSTALL_DIR" "$QWEN_TTS_HOST" "$QWEN_TTS_MODEL" "$LAUNCH_PATH" "${HF_HOME:-}"; do
  case "$value" in
    *[\&\<\>\"\']*) echo "Error: value must not contain & < > \" or ': $value" >&2; exit 1 ;;
  esac
done
for value in "$QWEN_TTS_PORT" "$QWEN_TTS_MAX_TOKENS" "$QWEN_TTS_LOG_MAX_BYTES" "$QWEN_TTS_LOG_BACKUPS"; do
  case "$value" in
    '' | *[!0-9]*) echo "Error: expected a positive integer: $value" >&2; exit 1 ;;
  esac
done

mkdir -p "$INSTALL_DIR/scripts" "$INSTALL_DIR/logs"
cp "$PACKAGE_DIR/scripts/hermes_tts_server.py" "$INSTALL_DIR/scripts/"
cp "$PACKAGE_DIR/scripts/hermes_tts_client.py" "$INSTALL_DIR/scripts/"
cp "$PACKAGE_DIR/scripts/healthcheck.sh" "$INSTALL_DIR/scripts/"
chmod 755 "$INSTALL_DIR/scripts/"*.py "$INSTALL_DIR/scripts/"*.sh

VENV="$INSTALL_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYTHON" -m venv "$VENV" || {
    echo "Could not create venv. Install uv and rerun, or create the venv first." >&2
    exit 1
  }
fi

# huggingface_hub>=1.10 provides `hf cache verify`, used by the server on start.
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$VENV/bin/python" 'mlx-audio[server]==0.6.1' 'huggingface_hub>=1.10'
else
  "$VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || {
    echo "pip/ensurepip unavailable. Install uv (brew install uv), then rerun:" >&2
    echo "  $0 \"$INSTALL_DIR\"" >&2
    exit 1
  }
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install 'mlx-audio[server]==0.6.1' 'huggingface_hub>=1.10'
fi

# launchd does not see the shell environment: pass a custom HF cache explicitly.
HF_HOME_ENTRY=""
if [ -n "${HF_HOME:-}" ]; then
  HF_HOME_ENTRY="<key>HF_HOME</key><string>$HF_HOME</string>"
fi

PLIST_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$PLIST_DIR"
PLIST="$PLIST_DIR/$LABEL.plist"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV/bin/python</string>
    <string>$INSTALL_DIR/scripts/hermes_tts_server.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>/dev/null</string>
  <key>StandardErrorPath</key><string>$INSTALL_DIR/logs/stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$LAUNCH_PATH</string>
    <key>QWEN_TTS_HOST</key><string>$QWEN_TTS_HOST</string>
    <key>QWEN_TTS_PORT</key><string>$QWEN_TTS_PORT</string>
    <key>QWEN_TTS_MODEL</key><string>$QWEN_TTS_MODEL</string>
    <key>QWEN_TTS_MAX_TOKENS</key><string>$QWEN_TTS_MAX_TOKENS</string>
    <key>QWEN_TTS_LOG_DIR</key><string>$INSTALL_DIR/logs</string>
    <key>QWEN_TTS_LOG_MAX_BYTES</key><string>$QWEN_TTS_LOG_MAX_BYTES</string>
    <key>QWEN_TTS_LOG_BACKUPS</key><string>$QWEN_TTS_LOG_BACKUPS</string>
    $HF_HOME_ENTRY
  </dict>
</dict>
</plist>
EOF

plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl enable "gui/$(id -u)/$LABEL"
launchctl bootstrap "gui/$(id -u)" "$PLIST"

URL="http://$QWEN_TTS_HOST:$QWEN_TTS_PORT"
echo
echo "Installed to: $INSTALL_DIR"
echo "LaunchAgent: $PLIST"
echo "Logs: $INSTALL_DIR/logs/server.log (rotated), stderr.log"
echo
echo "The server never downloads the model. Download it once (~4.5 GB):"
echo "  \"$VENV/bin/hf\" download $QWEN_TTS_MODEL"
echo "Until then the service exits and launchd retries every 60 s."
echo
echo "Health check (model verification and load take a while):"
echo "  curl $URL/health"
if [ "$URL" != "http://127.0.0.1:8031" ]; then
  echo "Non-default address: set QWEN_TTS_URL=$URL in the environment Hermes runs in."
fi
echo
echo "Hermes config snippet: $PACKAGE_DIR/config/tts.yaml"
echo "Merge it into ~/.hermes/config.yaml"
