#!/usr/bin/env bash
# 下载 3 个 frontrunner 世界模型 + 必要底座到 /mnt/local/sean/models/。
# hf download 默认断点续传；逐个下便于监控。smallest-first，最大的 JoyAI-LongVideo 垫底。
# 遇 401/gated：export HF_TOKEN=xxx 后重跑（续传不会重下）。
set -euo pipefail

HF=/mnt/local/envs/conda_envs/scene_service/bin/hf
DST=/mnt/local/sean/models

dl() {  # dl <repo> <local-dir-name>
  local repo="$1" name="$2"
  echo "==================== $repo -> $DST/$name ===================="
  "$HF" download "$repo" --local-dir "$DST/$name"
}

# 1) Matrix-Game 2.0（本体 ~28G，MIT）—— 真 LIVE / inference_streaming.py
dl Skywork/Matrix-Game-2.0 Matrix-Game-2.0

# 2) DreamX-World-5B（本体 21G + 底座 Wan2.2-TI2V-5B 34G）—— NL 事件驱动 / 慢速回合制
dl GD-ML/DreamX-World-5B DreamX-World-5B
dl Wan-AI/Wan2.2-TI2V-5B Wan2.2-TI2V-5B
# 可选相机控制版（+24.5G），需要再取消注释：
# dl GD-ML/DreamX-World-5B-Cam DreamX-World-5B-Cam

# 3) JoyAI-Echo —— Echo-WM 交互世界模型(96G) + LongVideo 身份+语音记忆(143G)
dl Echo-Team/Echo-WM Echo-WM
dl jdopensource/JoyAI-Echo JoyAI-Echo

echo "全部完成。落盘 $DST"
