#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sv0/sean/Ludens
source research/ludens_env.sh
export HF_HOME=/mnt/sv0/sean/cache/huggingface
export LUDENS_LIVE=1
export LUDENS_PORT="${LUDENS_PORT:-8794}"
export LUDENS_SFT_URL="${LUDENS_SFT_URL-}"
export LUDENS_VIDEO_URL="${LUDENS_VIDEO_URL:-http://127.0.0.1:8800}"
export LUDENS_CREATOR_IMAGE_URL="${LUDENS_CREATOR_IMAGE_URL:-http://127.0.0.1:18781}"
export LUDENS_IMAGE_URL="${LUDENS_IMAGE_URL:-$LUDENS_CREATOR_IMAGE_URL}"
export CUDA_VISIBLE_DEVICES=
exec /mnt/sv0/sean/envs/ludens-vllm-omni/bin/python -m pipeline.ludens_pipeline
