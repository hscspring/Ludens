#!/usr/bin/env bash
# JoyAI-Echo 1.5 推理环境(BF16 路径)。依据 README + requirements.txt 核实:
# torch 2.8.0 + cu128;三个本地包(ltx-core/ltx-pipelines/ltx-distillation)由 inference.py:20
# sys.path 注入,无需 pip install。直接用官方 requirements.txt(含 msst/serving deps,装了不用无害),
# 保证 omegaconf 等齐全。BF16 不碰 tensorrt_llm(FP8/FP4 才需要);attention 走 sdpa 兜底,不装 xformers/flash。
set -euo pipefail

CONDA=/mnt/local/envs/miniconda3/bin/conda
ENV=/mnt/local/envs/conda_envs/joyai-echo
REPO=/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo
PY="$ENV/bin/python"; PIP="$ENV/bin/pip"

echo "==================== 1) conda env (python 3.11) ===================="
[ -x "$PY" ] || "$CONDA" create -p "$ENV" python=3.11 -y

echo "==================== 2) torch 2.8.0 (cu128) ===================="
"$PIP" install --no-input torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu128

echo "==================== 3) requirements.txt(torch 已满足不重装;含 msst/serving deps) ===================="
"$PIP" install --no-input -r "$REPO/requirements.txt"

echo "==================== DONE ===================="
CUDA_VISIBLE_DEVICES=7 "$PY" -c "import torch, transformers, peft, av, omegaconf; print('torch', torch.__version__, '| cuda', torch.version.cuda, '| avail', torch.cuda.is_available(), '| transformers', transformers.__version__)"
