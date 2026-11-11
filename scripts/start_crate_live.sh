#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sv0/sean/Ludens
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/mnt/sv0/sean/Ludens/research/out/interactive_crate_20260923/tmp
export PYTHONPATH=/mnt/sv0/sean/Ludens/research/out/interactive_crate_20260923/tts:/mnt/sv0/sean/Ludens/research/out/interactive_crate_20260923/deps:/mnt/sv0/sean/envs/ludens-joyai/lib/python3.11/site-packages
export LUDENS_TTS_MODEL=/mnt/sv0/sean/models/Kokoro-82M-v1.1-zh-onnx
export LUDENS_PORT="${LUDENS_PORT:-8793}"
exec /mnt/sv0/sean/runtimes/cpython-3.11-ludens/bin/python3.11 -m pipeline.ludens_pipeline
