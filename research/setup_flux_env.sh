#!/usr/bin/env bash
# 在 sv0 重建 Ludens FLUX 出图 env(原 scene_service 在 /mnt/local 被 root 收权限=chmod 000 报废,local 下线中)。
# uv 建(CLAUDE.md 规范):standalone CPython 落 HOME,抗盘挂——正是 local 报废的教训。
# 版本钉旧 env 实测组合(读不了 .py 但 dist-info 目录名可读,抠出精确版本)。
# diffusers 原为 0.41.0.dev0(git main 快照,PyPI 无该 release);钉 PyPI 最新 stable 0.40.0=dev0 紧前一个 release,
# 可控、防 main 漂移;末尾 import smoke 验 FluxKontextPipeline 存在,不行再退 git main。
# 模型不重下(FLUX.1-Kontext-dev 已在 sv0)。装完 import + cuda smoke。
set -euo pipefail

source /mnt/sv0/sean/Ludens/research/ludens_env.sh  # cache 重指 sv0(local/gv0 已下线)

ENV=/mnt/sv0/sean/envs/ludens-flux
PY=3.11

uv venv "$ENV" --python "$PY" --clear  # 已存在则清空重建(幂等,重跑安全)

# torch:PyPI 默认 CUDA 构建(照原 setup.sh);driver 590/CUDA13.1 向后兼容 cu12x wheel。
uv pip install --python "$ENV/bin/python" \
    torch==2.14.0 torchvision==0.29.0 \
    diffusers==0.40.0 transformers==5.16.1 accelerate==1.14.0 \
    huggingface_hub==1.30.0 safetensors sentencepiece protobuf pillow

"$ENV/bin/python" - <<'PYEOF'
import torch, diffusers
from diffusers import FluxKontextPipeline  # 出图管线可导入=diffusers 版本够
ok = torch.cuda.is_available()
dev = torch.cuda.get_device_name(0) if ok else "-"
print(f"torch {torch.__version__} | cuda_avail={ok} | dev={dev}")
print(f"diffusers {diffusers.__version__} | FluxKontextPipeline import OK")
assert ok, "CUDA 不可用,torch wheel 与 driver 不匹配,需换 --torch-backend"
PYEOF
echo "env ready -> $ENV"
