#!/usr/bin/env bash
set -eu

cd /mnt/sv0/sean/Ludens
source research/ludens_env.sh
umask 002
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
PYTHON=/mnt/sv0/sean/runtimes/cpython-3.11-ludens/bin/python3.11
OUT=/mnt/sv0/sean/Ludens/research/out/character_layers_20260923
COMMON=(--host doams-185 --out-dir "$OUT/person"
  --site /mnt/sv0/sean/Ludens/pipeline/tavern/static/character-routes-20260923/person
  --image "$OUT/inputs/person_reference_gray.png" --prompt-file "$OUT/inputs/person.prompt.txt")

CUDA_VISIBLE_DEVICES=2 "$PYTHON" research/run_video_quality.py echo_flash ltx_distilled "${COMMON[@]}" > "$OUT/person/batch_gpu2.log" 2>&1 &
P2=$!
CUDA_VISIBLE_DEVICES=3 "$PYTHON" research/run_video_quality.py ltx_full "${COMMON[@]}" > "$OUT/person/batch_gpu3.log" 2>&1 &
P3=$!
CUDA_VISIBLE_DEVICES=4 "$PYTHON" research/run_video_quality.py joy "${COMMON[@]}" > "$OUT/person/batch_gpu4.log" 2>&1 &
P4=$!
CUDA_VISIBLE_DEVICES=6 "$PYTHON" research/run_video_quality.py minimax "${COMMON[@]}" > "$OUT/person/batch_gpu6.log" 2>&1 &
P6=$!
RESULT=0
for PID in "$P2" "$P3" "$P4" "$P6"; do
  wait "$PID" || RESULT=1
done
exit "$RESULT"
