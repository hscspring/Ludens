#!/usr/bin/env bash
# scene_service 环境 + 权重准备（用户 review 后手动跑；下载 ~24GB Kontext + ~数十GB LTX）
#
# 前置（手动、一次性）：
#   - FLUX.2-klein-4B：Apache 2.0，ungated，默认图像渲染器，无需点 license
#   - https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev  备选渲染器，需接受非商用 license
#   - https://huggingface.co/Lightricks/LTX-2.5-Diffusers          需接受 LTX Community license
#   - 终端登录：在 Claude 提示框输入  ! hf auth login   （或本脚本外自己 hf auth login）
set -euo pipefail

ENV=/mnt/local/envs/conda_envs/scene_service
MODELS=/mnt/local/sean/models   # 本地盘：gv0 是共享盘，几十 GB 权重放上去容易卡死
CONDA=/mnt/local/envs/miniconda3/bin/conda

[ -x "$ENV/bin/python" ] || $CONDA create -p "$ENV" python=3.11 -y

# torch：默认 CUDA 构建；如需匹配本机驱动改 --index-url（如 cu128 用 blackwell 卡）
"$ENV/bin/pip" install torch torchvision

# diffusers 装 main 分支：FluxKontextPipeline / LTX2Pipeline 都需要
"$ENV/bin/pip" install \
    "git+https://github.com/huggingface/diffusers.git" \
    transformers accelerate safetensors sentencepiece protobuf \
    imageio imageio-ffmpeg av pillow "huggingface_hub[cli]" \
    fastapi uvicorn   # av(PyAV)：LTX2 图像条件化做 H.264 CRF 重压缩必需；fastapi/uvicorn 留给后续 server.py

# 权重（本地路径，别用 HF remote name）
# klein 仓库含一份 native 单文件(flux-2-klein-4b.safetensors, 7.75G)，diffusers 版用不到，exclude 掉
"$ENV/bin/hf" download black-forest-labs/FLUX.2-klein-4B    --local-dir "$MODELS/FLUX.2-klein-4B" \
    --exclude "flux-2-klein-4b.safetensors"
"$ENV/bin/hf" download black-forest-labs/FLUX.1-Kontext-dev --local-dir "$MODELS/FLUX.1-Kontext-dev"
"$ENV/bin/hf" download Lightricks/LTX-2.5-Diffusers        --local-dir "$MODELS/LTX-2.5-Diffusers"

echo "done. smoke（默认 klein@1024²）:"
echo "  $ENV/bin/python replay.py --session /mnt/local/sean/davr_mt/run_davr/demo/sessions/771abfe3811a --out out/771"
