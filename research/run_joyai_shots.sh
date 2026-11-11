#!/usr/bin/env bash
# 出片:把 research/r2v_requests/ 里的 R2V 请求喂给 JoyAI-Echo 出视频。
# 单 shot = 单卡(BF16 吃满 ~80G,只能用全空卡);多个 shot 相互独立(memory_slots=[]),可多卡并行或单卡串行。
#
# 用法:
#   bash run_joyai_shots.sh 7        # 单卡串行(授权区 7,最稳,3 个 shot 顺序跑)
#   bash run_joyai_shots.sh 0 1 7    # 三卡并行(0/1 是训练区,用前自己确认没在训)
#
# round-robin 把 request 分给各卡:同一张卡上的一组串行跑(不爆显存),卡之间并行。
set -euo pipefail

ENV=/mnt/local/envs/conda_envs/joyai-echo
REPO=/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo
REQ_DIR=/mnt/local/sean/Ludens/research/r2v_requests
CONFIG=configs/inference.smoke_bf16.yaml
LOG_DIR=/mnt/local/sean/Ludens/research/out/joyai_logs
OUT_ROOT=/mnt/local/sean/Ludens/research/smoke_out/joyai  # config.output_root,按 work_id/shot_id 分目录

GPUS=("$@"); [ ${#GPUS[@]} -eq 0 ] && GPUS=(7)
mkdir -p "$LOG_DIR"
mapfile -t REQS < <(ls "$REQ_DIR"/shot_*.json | sort)
[ ${#REQS[@]} -eq 0 ] && { echo "no requests in $REQ_DIR"; exit 1; }
cd "$REPO"

echo "GPUs=${GPUS[*]}  shots=${#REQS[@]}  config=$CONFIG"

run_on_gpu() {          # $1=gpu;后续=分给这张卡的 request(同卡串行)
  local gpu=$1; shift
  for req in "$@"; do
    local name; name=$(basename "$req" .json)
    echo "[$name] -> GPU $gpu  (log: $LOG_DIR/$name.gpu$gpu.log)"
    CUDA_VISIBLE_DEVICES="$gpu" "$ENV/bin/python" inference.py \
      --config "$CONFIG" --request "$req" > "$LOG_DIR/$name.gpu$gpu.log" 2>&1
    echo "[$name] done on GPU $gpu"
  done
}

for g in "${!GPUS[@]}"; do
  group=()
  for i in "${!REQS[@]}"; do
    [ $(( i % ${#GPUS[@]} )) -eq "$g" ] && group+=("${REQS[$i]}")
  done
  [ ${#group[@]} -eq 0 ] && continue
  run_on_gpu "${GPUS[$g]}" "${group[@]}" &
done
wait

echo "all shots done. videos under $OUT_ROOT/ludens-denji-demo/<shot_id>/"
