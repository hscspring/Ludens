#!/usr/bin/env bash
# 下载 MiniMax-H3 单任务族到 /mnt/local/sean/models/MiniMax-H3。
# H3 = 官方 omni 视频生成(image-text-to-video)。仓库 FL2VA / Ref2VA 两个自包含任务族并列,
# 各含 processor/tokenizer/text_encoder/transformer/visual_vae/audio_vae,单族 ~150G。
# 不 gated,公开可下,无需 token。hf download 默认断点续传,断了重跑即可(不重下)。
set -euo pipefail

PY=/mnt/local/envs/conda_envs/scene_service/bin/python
REPO=MiniMaxAI/MiniMax-H3
DST=/mnt/local/sean/models/MiniMax-H3

# 新版 hf CLI 的 `--include a b` 会把后一个 pattern 当显式文件名(去下字面 FL2VA/* → 404),
# 改用 huggingface_hub.snapshot_download + allow_patterns,断点续传内置、fnmatch 递归匹配。
# FL2VA:文生视频 + 首帧/尾帧→视频,~150G,先下;Ref2VA(锁身份)之后把 allow 加 "Ref2VA/*" 即可。
"$PY" - "$REPO" "$DST" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download
repo, dst = sys.argv[1], sys.argv[2]
snapshot_download(repo_id=repo, local_dir=dst, max_workers=8,
                  allow_patterns=["model_index.json", "FL2VA/*"])
print("FL2VA 下载完成 ->", dst)
PYEOF
