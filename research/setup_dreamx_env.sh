#!/usr/bin/env bash
# DreamX-World-5B(AR-forcing)推理环境。依据 requirements.txt + inference_ar_forcing.sh 核实:
# torch 2.5.1 + cu124;flash_attn 是 wan/modules/attention.py 硬 import(FA2/FA3)。
# 跳过 xfuser/gradio/tensorboard/onnxruntime/datasets/albumentations/librosa/tomesd/bs4/wcwidth
# (AR 推理路径不 import,agent rg 核实);triton 用 torch 自带。
set -euo pipefail

CONDA=/mnt/local/envs/miniconda3/bin/conda
ENV=/mnt/local/envs/conda_envs/dreamx-world
PY="$ENV/bin/python"; PIP="$ENV/bin/pip"

echo "==================== 1) conda env (python 3.10) ===================="
[ -x "$PY" ] || "$CONDA" create -p "$ENV" python=3.10 -y

echo "==================== 2) torch 2.5.1 (cu124) ===================="
"$PIP" install --no-input torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124

echo "==================== 3) 推理核心依赖 ===================="
"$PIP" install --no-input \
  einops safetensors timm torchdiffeq torchsde decord "numpy<2" scipy scikit-image \
  opencv-python omegaconf sentencepiece "imageio[ffmpeg]" "imageio[pyav]" \
  "accelerate>=0.25.0" "diffusers>=0.30.1" "transformers>=4.46.2" Pillow ftfy func_timeout

echo "==================== 4) flash-attn(预编译 wheel,ABI 兼容 torch2.5) ===================="
"$PIP" install --no-input flash-attn --no-build-isolation

echo "==================== DONE ===================="
CUDA_VISIBLE_DEVICES=7 "$PY" -c "import torch, flash_attn, diffusers, transformers; print('torch', torch.__version__, '| cuda', torch.version.cuda, '| avail', torch.cuda.is_available(), '| flash_attn', flash_attn.__version__)"
