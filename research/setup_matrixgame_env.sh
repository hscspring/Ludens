#!/usr/bin/env bash
# 为 Matrix-Game 2.0 建独立 conda env 并装「推理」所需依赖。
# 依据源码 rg 结果精简:只有 flash-attn 是硬 import(action_module.py:3);
# tensorrt/pycuda/onnx 仅 demo_utils 的 trt 加速版 VAE 用(推理走 vae_block3.py,不碰);
# apex 全仓库无 import(README 让装是训练用);flask/wandb 是 web/训练用 —— 全跳过。
# env 位置遵循 CLAUDE.md:/mnt/local/envs/conda_envs/<项目名>/
set -euo pipefail

CONDA=/mnt/local/envs/miniconda3/bin/conda
ENV=/mnt/local/envs/conda_envs/matrix-game-2.0
REPO=/mnt/local/sean/wm_repos/Matrix-Game/Matrix-Game-2

echo "==================== 1) 建 conda env (python 3.10) ===================="
[ -x "$ENV/bin/python" ] || "$CONDA" create -p "$ENV" python=3.10 -y
PY="$ENV/bin/python"; PIP="$ENV/bin/pip"

echo "==================== 2) torch 2.6.0 (cu124) ===================="
# 代码用 torch.nn.attention.flex_attention(action_module/causal_model:需 torch>=2.5);README 的 >=2.4 写错
"$PIP" install --no-input torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124

echo "==================== 3) 推理核心依赖 ===================="
"$PIP" install --no-input \
  diffusers "transformers>=4.49.0" "tokenizers>=0.20.3" "accelerate>=1.1.1" \
  omegaconf einops av safetensors "opencv-python>=4.9.0.80" imageio imageio-ffmpeg \
  easydict ftfy open_clip_torch sentencepiece scikit-image dominate numpy tqdm \
  "huggingface_hub[cli]" dashscope

echo "==================== 4) openai CLIP ===================="
"$PIP" install --no-input git+https://github.com/openai/CLIP.git

echo "==================== 5) flash-attn (预编译 wheel 优先) ===================="
"$PIP" install --no-input flash-attn --no-build-isolation

echo "==================== 6) setup.py develop ===================="
cd "$REPO" && "$PY" setup.py develop

echo "==================== DONE ===================="
"$PY" -c "import torch, flash_attn, diffusers, transformers; print('torch', torch.__version__, '| cuda avail', torch.cuda.is_available(), '| flash_attn', flash_attn.__version__)"
