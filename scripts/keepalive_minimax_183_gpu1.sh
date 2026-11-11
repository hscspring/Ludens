#!/usr/bin/env bash
set -euo pipefail
cd /mnt/sv0/sean/Ludens
exec 9>research/out/minimax_183_gpu1_keepalive/request.lock
/usr/bin/flock -n 9 || exit 0
date -u '+%Y-%m-%dT%H:%M:%SZ MiniMax 183 GPU 1 keepalive'
/usr/bin/curl --fail-with-body --silent --show-error --connect-timeout 10 --max-time 240 \
  http://127.0.0.1:8800/v1/videos/sync \
  --form-string 'prompt=Continue the reference frame. Locked camera. The character stays still with subtle breathing. Preserve face, clothes, objects and background. No speech, no text.' \
  --form-string 'width=672' --form-string 'height=384' \
  --form-string 'fps=24' --form-string 'seed=7' \
  --form-string 'num_inference_steps=8' --form-string 'flow_shift=12' \
  --form-string 'extra_params={"task":"fl2va","duration":5,"audio_flow_shift":3.0}' \
  --form-string 'lora={"name":"h3-turbo8","path":"/mnt/sv0/sean/models/MiniMax-H3-Turbo/minimax_h3_fl2v_turbo_8step_v1.0_bf16.safetensors","scale":1.0}' \
  --form 'input_reference=@research/out/roleplay_live_20260925/media/hozumi/frame.webp;type=image/webp' \
  --output /dev/null --write-out 'HTTP %{http_code}, %{time_total}s, %{size_download} bytes\n'
