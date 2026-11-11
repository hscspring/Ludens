#!/usr/bin/env bash
# Echo-WM 推理环境。依据 echo_wm/requirements.txt + README.md 核实:
# torch 2.9.1 + cu128(与 Matrix-Game 的 cu124 不同);transformers<5.0;gemma-3 当文字编码器。
# 跳过 gradio/matplotlib(UI,命令行 smoke 不用);无 flash-attn(全仓库无 import,走 xformers/sdpa)。
set -euo pipefail

CONDA=/mnt/local/envs/miniconda3/bin/conda
ENV=/mnt/local/envs/conda_envs/echo-wm
PY="$ENV/bin/python"; PIP="$ENV/bin/pip"

echo "==================== 1) conda env (python 3.11) ===================="
[ -x "$PY" ] || "$CONDA" create -p "$ENV" python=3.11 -y

echo "==================== 2) torch 2.9.1 (cu128) ===================="
"$PIP" install --no-input torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 \
  --index-url https://download.pytorch.org/whl/cu128

echo "==================== 3) 推理核心依赖(跳过 gradio/matplotlib UI) ===================="
"$PIP" install --no-input \
  einops numpy "transformers>=4.52,<5.0" safetensors accelerate "scipy>=1.14" \
  opencv-python imageio imageio-ffmpeg av pillow tqdm pyyaml omegaconf \
  "huggingface-hub<1.0" sentencepiece protobuf

echo "==================== 4) xformers(可选加速,失败即跳过) ===================="
"$PIP" install --no-input xformers==0.0.33.post2 || echo "[WARN] xformers 装失败,跳过(推理仍可跑)"

echo "==================== DONE ===================="
CUDA_VISIBLE_DEVICES=7 "$PY" -c "import torch, transformers; print('torch', torch.__version__, '| cuda', torch.version.cuda, '| avail', torch.cuda.is_available(), '| transformers', transformers.__version__)"
