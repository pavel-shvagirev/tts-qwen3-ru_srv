#!/bin/sh
set -eu
URL="${QWEN_TTS_URL:-http://127.0.0.1:8031}"
curl --fail --silent --show-error "$URL/health"
printf '\n'
