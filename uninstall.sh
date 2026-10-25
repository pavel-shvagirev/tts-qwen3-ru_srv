#!/bin/sh
set -eu
LABEL="local.tts-ru.hermes-qwen3-tts"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SERVICE="gui/$(id -u)/$LABEL"
STOP_TIMEOUT=30  # launchd sends SIGKILL after its own 20 s ExitTimeOut

# Stop the server before removing its LaunchAgent: bootout sends SIGTERM and
# unloads the job, so KeepAlive does not restart it.
if launchctl print "$SERVICE" >/dev/null 2>&1; then
  PID=$(launchctl print "$SERVICE" | awk '$1 == "pid" && $2 == "=" { print $3; exit }')
  launchctl bootout "$SERVICE"
  if [ -n "$PID" ]; then
    waited=0
    while kill -0 "$PID" 2>/dev/null; do
      if [ "$waited" -ge "$STOP_TIMEOUT" ]; then
        echo "Error: server (pid $PID) still running after ${STOP_TIMEOUT} s; LaunchAgent kept: $PLIST" >&2
        exit 1
      fi
      sleep 1
      waited=$((waited + 1))
    done
    echo "Stopped server (pid $PID)."
  else
    echo "Service was loaded but not running."
  fi
else
  echo "Service $LABEL is not loaded."
fi

rm -f "$PLIST"
echo "Removed LaunchAgent. App files and downloaded Hugging Face model cache were preserved."
echo "To remove app files manually, delete the installation directory you chose."
