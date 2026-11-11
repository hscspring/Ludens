#!/usr/bin/env bash
# 起 JoyAI-Echo 官方常驻 server(Ludens 视频侧后端)。
# GPU7 单卡:Sean 训练占 0-6,Ludens 只剩 GPU7。硬编码 CUDA_VISIBLE_DEVICES=7(不用 fallback,防 shell 环境污染)。
# 配套 server.ludens.bf16.gpu7.yaml 里 runtime.gpu_ids=[0](物理7→逻辑0),1 个常驻 worker。
# 腾出更多卡后:改回 CUDA_VISIBLE_DEVICES=0..7 + config 指回 server.ludens.bf16.yaml。
set -euo pipefail

export CUDA_VISIBLE_DEVICES=7
source /mnt/sv0/sean/Ludens/research/ludens_env.sh

JOYAI_ROOT=/mnt/sv0/sean/wm_repos/JoyAI-Echo/echo_longvideo
JOYAI_PY=/mnt/sv0/sean/envs/ludens-joyai/bin/python

cd "$JOYAI_ROOT"
exec "$JOYAI_PY" -m server --config configs/server.ludens.bf16.gpu7.yaml "$@"
