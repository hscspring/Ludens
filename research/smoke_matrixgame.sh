#!/usr/bin/env bash
# Matrix-Game 2.0 smoke:GPU7,universal 场景,自带默认起始图,随机动作轨迹 → 短交互视频。
# 用 batch 版 inference.py(inference_streaming.py 需交互式喂图/动作,不适合无人值守 smoke)。
set -euo pipefail

ENV=/mnt/local/envs/conda_envs/matrix-game-2.0
REPO=/mnt/local/sean/wm_repos/Matrix-Game/Matrix-Game-2
MODELS=/mnt/local/sean/models/Matrix-Game-2.0
OUT=/mnt/local/sean/Ludens/research/smoke_out/matrixgame
FRAMES="${1:-81}"   # 81 帧 ≈ 3.2s@25fps;想更长传参覆盖

mkdir -p "$OUT"
cd "$REPO"
CUDA_VISIBLE_DEVICES=7 "$ENV/bin/python" inference.py \
  --config_path configs/inference_yaml/inference_universal.yaml \
  --checkpoint_path "$MODELS/base_distilled_model/base_distill.safetensors" \
  --img_path demo_images/universal/0000.png \
  --output_folder "$OUT" \
  --num_output_frames "$FRAMES" \
  --seed 42 \
  --pretrained_model_path "$MODELS"
