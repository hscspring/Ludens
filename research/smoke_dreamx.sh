#!/usr/bin/env bash
# DreamX-World-5B AR-forcing smoke:单卡,21 latent 帧(=81 pixel,5s@16fps),第1个 demo 样本。
# 直接调 inference_ar_forcing.py(.sh 硬写 252 帧=60s 太长做 smoke);权重路径全 CLI 传,不改 yaml。
set -euo pipefail

GPU="${1:-7}"   # 传目标卡号,默认 7
ENV=/mnt/local/envs/conda_envs/dreamx-world
REPO=/mnt/local/sean/wm_repos/DreamX-World
MODELS=/mnt/local/sean/models
OUT=/mnt/local/sean/Ludens/research/smoke_out/dreamx
mkdir -p "$OUT"

# 单样本 smoke json(只跑第 1 条,避免 16 条全跑)
"$ENV/bin/python" -c "
import json
d=json.load(open('$REPO/configs/dreamx/eval.json'))
json.dump([d[0]], open('$REPO/configs/dreamx/smoke1.json','w'), ensure_ascii=False, indent=2)
print('smoke1.json:', d[0]['image_path'])
"

cd "$REPO"
CUDA_VISIBLE_DEVICES="$GPU" "$ENV/bin/python" inference_ar_forcing.py \
  --config_path configs/dreamx-ar/causal_camera_forcing_5b.yaml \
  --model_name "$MODELS/Wan2.2-TI2V-5B" \
  --transformer_path "$REPO/configs/dreamx-ar/" \
  --base_checkpoint_path "$MODELS/DreamX-World-5B/model.safetensors" \
  --data_path configs/dreamx/smoke1.json \
  --output_folder "$OUT" \
  --num_output_frames 21 \
  --fps 16 \
  --seed 42 \
  --color_correction_strength 1.0 \
  --chunk_relative
