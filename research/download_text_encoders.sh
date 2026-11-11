#!/usr/bin/env bash
# 下载 Echo-WM / JoyAI-Echo 需要的 gemma-3 文字编码器(两个变体,各 ~24G)。
# 已确认缓存 token(user=EvilYam@kaonai)可访问这两个 gated 仓库。hf download 断点续传。
set -euo pipefail

HF=/mnt/local/envs/conda_envs/scene_service/bin/hf
DST=/mnt/local/sean/models

dl() { echo "==================== $1 -> $DST/$2 ===================="; "$HF" download "$1" --local-dir "$DST/$2"; }

# JoyAI-Echo LongVideo → 标准版
dl google/gemma-3-12b-it gemma-3-12b-it
# Echo-WM → QAT 反量化版(bf16 载入)
dl google/gemma-3-12b-it-qat-q4_0-unquantized gemma-3-12b-it-qat-q4_0-unquantized

echo "文字编码器下载完成。落盘 $DST"
