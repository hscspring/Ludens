#!/usr/bin/env bash
set -euo pipefail
umask 0002
PROJECT=/mnt/sv0/sean/Ludens
OUT="$PROJECT/research/out/state_continuity_20260925"
PY=/mnt/sv0/sean/runtimes/cpython-3.11-ludens/bin/python3.11
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:?Specify an approved GPU}" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 OMP_NUM_THREADS=8
LUDENS_RUN_CACHE="$OUT/cache_183_gpu${CUDA_VISIBLE_DEVICES}"
export XDG_CACHE_HOME="$LUDENS_RUN_CACHE" TMPDIR="$LUDENS_RUN_CACHE" HF_HOME="$LUDENS_RUN_CACHE/huggingface"
export CUDA_CACHE_PATH="$TMPDIR/cuda" TRITON_CACHE_DIR="$TMPDIR/triton"
export TORCHINDUCTOR_CACHE_DIR="$TMPDIR/inductor" TORCH_HOME="$TMPDIR/torch"
export NUMBA_CACHE_DIR="$TMPDIR/numba" MPLCONFIGDIR="$TMPDIR/matplotlib"
export PATH="$PROJECT/research/out/video_quality_20260922/bin:$PATH"
mkdir -p "$TMPDIR"
if [ "$#" -eq 0 ]; then
    printf 'Pass one action-test profile\n' >&2
    exit 2
fi
for PROFILE in "$@"; do
    BACKEND=ludens-flux
    EXTRA="$PROJECT/research/out/acceleration_20260924/deps:"
    if [[ "$PROFILE" == joy_* ]]; then
        BACKEND=ludens-joyai
        EXTRA=""
    fi
    export PYTHONPATH="${EXTRA}$PROJECT/research/out/video_quality_20260922/network-deps:$PROJECT/research/out/video_quality_20260922/extras:$PROJECT/research/out/character_180_20260922/extras:/mnt/sv0/sean/envs/$BACKEND/lib/python3.11/site-packages"
    if "$PY" "$PROJECT/research/story_eval.py" --story "$OUT/$PROFILE/story.json" \
        --site "$PROJECT/pipeline/tavern/static/state-continuity-20260925/$PROFILE" > "$OUT/$PROFILE/${LUDENS_LOG_NAME:-run.log}" 2>&1; then
        printf '%s completed\n' "$PROFILE"
    else
        CODE=$?
        "$PY" - "$PROJECT/pipeline/tavern/static/state-continuity-20260925/$PROFILE/results.json" "$CODE" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = json.loads(p.read_text())
data.update(status='waiting' if sys.argv[2] == '75' else 'failed', exit_code=int(sys.argv[2]))
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
PY
        exit "$CODE"
    fi
done
