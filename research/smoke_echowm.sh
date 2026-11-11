#!/usr/bin/env bash
# Echo-WM 交互式 I2V 世界模型 smoke:单卡,官方 case 0010(峡谷水潭,action w-a-w-d)。
# run_wm_case.py 读 case.json+input.png → 起 inference_wm.py 子进程;case 带 fov_deg 70 故不触发 MoGe-2。
# 关 action-overlay(不把 WASD 图标叠画面上,纯看世界连续性)。
set -euo pipefail

GPU="${1:-7}"   # 传目标卡号,默认 7
ENV=/mnt/local/envs/conda_envs/echo-wm
REPO=/mnt/local/sean/wm_repos/JoyAI-Echo/echo_wm
MODELS=/mnt/local/sean/models
OUT=/mnt/local/sean/Ludens/research/smoke_out/echowm
mkdir -p "$OUT"

cd "$REPO"
CUDA_VISIBLE_DEVICES="$GPU" "$ENV/bin/python" scripts/run_wm_case.py \
  --case examples/wm_cases/0010 \
  --checkpoint "$MODELS/Echo-WM/echo-wm-base.safetensors" \
  --gemma-path "$MODELS/gemma-3-12b-it-qat-q4_0-unquantized" \
  --output-dir "$OUT" \
  --no-action-overlay
