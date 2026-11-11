#!/usr/bin/env bash
set -euo pipefail
export CUDA_VISIBLE_DEVICES=0,1,6,7
export PYTHONPATH=/mnt/sv0/sean
export TORCHDYNAMO_DISABLE=1 OMP_NUM_THREADS=8 VLLM_USE_FLASHINFER_SAMPLER=0
export TRITON_CACHE_MANAGER=training.common.triton_cache:ProcessIsolatedFileCacheManager
export TRITON_CACHE_DIR=/mnt/sv0/sean/outputs/ludens/sft-serve-tp4-20261016/triton-cache
export FLASHINFER_WORKSPACE_BASE=/mnt/sv0/sean/outputs/ludens/sft-serve-tp4-20261016
export FLASHINFER_CUBIN_DIR=/mnt/sv0/sean/outputs/ludens/eval-v1/flashinfer-cubins
mkdir -p "$FLASHINFER_WORKSPACE_BASE"
echo "$$" > "$FLASHINFER_WORKSPACE_BASE/server.pid"
exec /mnt/sv0/sean/envs/aim-swift-4.4.2/bin/python -u -m vllm.entrypoints.openai.api_server \
  --model /mnt/sv0/sean/outputs/ludens/sft-v1-offload/checkpoint-121-hf \
  --served-model-name ludens-sft-v1 --host 127.0.0.1 --port 8890 \
  --tensor-parallel-size 4 --dtype bfloat16 --max-model-len 14336 --max-num-seqs 4 \
  --gpu-memory-utilization 0.5 --enforce-eager --no-async-scheduling \
  --attention-config '{"backend":"FLASH_ATTN"}' --kernel-config '{"moe_backend":"triton"}' \
  --limit-mm-per-prompt '{"image":0,"video":0,"audio":0}' \
  --default-chat-template-kwargs '{"enable_thinking":false}' \
  --generation-config vllm --safetensors-load-strategy prefetch \
  >> "$FLASHINFER_WORKSPACE_BASE/server.log" 2>&1
