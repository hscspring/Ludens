#!/usr/bin/env bash
# Ludens 所有命令统一 source:把被下线盘(local/gv0)劫持的 cache 环境变量重指到可写的 sv0。
# 系统 profile 把 XDG_CACHE_HOME/UV/CUDA/TRITON/TORCHINDUCTOR/NUMBA/MPL 指向 /mnt/local/cache,
# TORCH_HOME 指向 /mnt/gv0/cache(都已下线不可写)。只在 Ludens 命令内局部覆盖,不改系统 profile(不碰其他任务)。
BASE=/mnt/sv0/sean/.cache
export XDG_CACHE_HOME="$BASE/xdg"
export UV_CACHE_DIR="$BASE/uv"
export CUDA_CACHE_PATH="$BASE/cuda"
export TRITON_CACHE_DIR="$BASE/triton"
export TORCHINDUCTOR_CACHE_DIR="$BASE/torch/inductor"
export TORCH_HOME="$BASE/torch"
export NUMBA_CACHE_DIR="$BASE/numba"
export MPLCONFIGDIR="$BASE/matplotlib"
# HF_HOME 已是 /home/sean/.cache/huggingface(HOME 可写),不动
mkdir -p "$XDG_CACHE_HOME" "$UV_CACHE_DIR" "$CUDA_CACHE_PATH" "$TRITON_CACHE_DIR" \
         "$TORCHINDUCTOR_CACHE_DIR" "$TORCH_HOME" "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR"
