#!/usr/bin/env bash
# JoyAI-Echo 1.5 long-video smoke:单卡 BF16(echo15_full_dmd,绕开 FP8/trtllm)。
# 只跑 1 个 shot(--request 单 json,shot_001 memory_slots=[] 可独立跑);voice_filter 已在 smoke config 关掉。
# 输出 241 帧 / 736x1280 / 25fps ≈ 9.6s 长镜头(cafe 场景,Nathan Vale)。
set -euo pipefail

GPU="${1:-7}"   # 传目标卡号,默认 7
ENV=/mnt/local/envs/conda_envs/joyai-echo
REPO=/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo
OUT=/mnt/local/sean/Ludens/research/smoke_out/joyai
mkdir -p "$OUT"

cd "$REPO"
CUDA_VISIBLE_DEVICES="$GPU" "$ENV/bin/python" inference.py \
  --config configs/inference.smoke_bf16.yaml \
  --request examples/the_last_visa/requests/001_01_shot_001.json
