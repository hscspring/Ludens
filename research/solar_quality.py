import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace

cache = "/mnt/sv0/sean/Ludens/research/out/video_quality_20260922/cache_" + os.uname().nodename.replace("-", "")
Path(cache).mkdir(exist_ok=True)
os.environ.update(XDG_CACHE_HOME=cache, HF_HOME=cache + "/huggingface",
                  TORCHINDUCTOR_CACHE_DIR=cache + "/inductor", TRITON_CACHE_DIR=cache + "/triton",
                  CUDA_CACHE_PATH=cache + "/cuda", TMPDIR=cache)

local = int(os.environ.get("LOCAL_RANK", 0))
gpu = os.environ["CUDA_VISIBLE_DEVICES"].split(",")[local]
assert gpu in {"2", "3", "4", "5", "6", "7"}
occupants = subprocess.check_output(["nvidia-smi", f"--id={gpu}", "--query-compute-apps=pid",
                                     "--format=csv,noheader,nounits"], text=True).strip()
if occupants:
    raise SystemExit(f"GPU {gpu} is occupied; SolarWM did not start.")

import torch
import torch.distributed as dist
import peft
import yaml

from solarwm.backends.minimax_h3 import full_inference
from solarwm.backends.minimax_h3.demo_conditions import prepare_demo
from solarwm.backends.minimax_h3.distributed import init_sequence_parallel
from solarwm.backends.minimax_h3.official_codec import OfficialH3Codec
from solarwm.backends.minimax_h3.optional import load_conditioners

out = Path('/mnt/sv0/sean/Ludens/research/out/video_quality_20260922')
config = yaml.safe_load((out / 'solar_config.yaml').read_text())
inference = config['inference']
args = SimpleNamespace(config=config, plan=inference['plan'], work_dir=inference['work_dir'],
                       dataset_root=inference['dataset_root'], model_dir=config['model']['checkpoint_path'],
                       checkpoint=config['checkpoint']['resume_from'], weight_source='ema',
                       silence=config['data']['silence_latents_path'], output_dir=config['runtime']['output_dir'],
                       expected_step=3900, fps_policy='source', noise_seed=7)
torch.set_num_threads(8)
torch.cuda.set_device(local)
device = torch.device('cuda', local)
if sys.argv[1] == 'prepare':
    modules = load_conditioners(config['model'], device=device, schedulers=False)
    codec = OfficialH3Codec(text_encoder=modules.text_encoder, tokenizer=modules.tokenizer,
                           processor=modules.processor, video_vae=modules.video_vae,
                           audio_vae=modules.audio_vae, device=device, encoder_identity='official-minimax-h3')
    with torch.inference_mode():
        Path(args.silence).write_bytes(codec.silence_artifact_bytes())
        prepare_demo(json.loads(Path(args.plan).read_text())[0], args, modules, device)
else:
    assert sys.argv[1] == 'generate'
    print(f'Runtime: torch={torch.__version__}, peft={peft.__version__}', flush=True)
    dist.init_process_group('nccl', device_id=device, timeout=timedelta(minutes=5))
    init_sequence_parallel(config['distributed']['sequence_parallel_size'])
    full_inference.generate(args)
