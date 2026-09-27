#!/bin/bash

set -e

export DENO_INSTALL="$(pwd)/.deno"
export PATH="$DENO_INSTALL/bin:$PATH"

echo "================================="
echo "Starting VidSeek"
echo "================================="

echo "Deno:"
deno --version

echo "yt-dlp:"
yt-dlp --version

echo "Starting bgutil PO Token provider..."

cd "$(pwd)/bgutil-ytdlp-pot-provider/server"

deno run \
  --allow-env \
  --allow-net \
  --allow-ffi=. \
  --allow-read=. \
  src/main.ts \
  --host 127.0.0.1 \
  --port 4416 &

BGUTIL_PID=$!

echo "Bgutil PID: $BGUTIL_PID"

sleep 5

echo "Checking bgutil..."

if ! kill -0 $BGUTIL_PID 2>/dev/null; then
    echo "ERROR: bgutil provider failed to start"
    exit 1
fi

echo "Bgutil provider is running."

cd -

echo "Starting Gunicorn..."

PORT=${PORT:-8080}
exec gunicorn --bind "0.0.0.0:$PORT" --workers 1 --threads 2 --timeout 600 app:app
