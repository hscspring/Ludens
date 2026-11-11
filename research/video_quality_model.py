import argparse
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter

parser = argparse.ArgumentParser()
parser.add_argument('model')
parser.add_argument('--out-dir', type=Path, default=Path('/mnt/sv0/sean/Ludens/research/out/video_quality_20260922'))
parser.add_argument('--image', type=Path, default=Path('/mnt/sv0/sean/Ludens/research/out/opening/opening_tavern_seed7_v1.png'))
parser.add_argument('--prompt-file', type=Path)
parser.add_argument('--seed', type=int, default=7)
parser.add_argument('--fps', type=int, default=24)
parser.add_argument('--num-frames', type=int, default=121)
parser.add_argument('--audio', type=Path)
parser.add_argument('--width', type=int)
parser.add_argument('--height', type=int)
args = parser.parse_args()
if args.width is not None or args.height is not None:
    if args.model != 'minimax' or not args.width or not args.height or args.width % 32 or args.height % 32:
        parser.error('Explicit dimensions currently require MiniMax and two positive multiples of 32')
if args.model == 'wan_s2v' and args.audio is None:
    parser.error('wan_s2v requires --audio')
if (args.fps, args.num_frames) != (24, 121) and args.model not in {'ltx_full', 'ltx_distilled'}:
    parser.error('Frame rate overrides are supported only for LTX models')
if args.fps <= 0 or args.num_frames < 9 or (args.num_frames - 1) % 8:
    parser.error('Use positive FPS and 8n+1 frames, with n >= 1')
if args.seed != 7 and args.model not in {'ltx_full', 'ltx_distilled'}:
    parser.error('Non-default seeds are currently supported only for LTX models')
gpu = os.environ['CUDA_VISIBLE_DEVICES']
assignments = args.out_dir / 'gpu_assignments.json'
if assignments.exists():
    assigned = json.loads(assignments.read_text()).get(args.model)
    if assigned is not None and str(assigned) != gpu:
        print(f'{sys.argv[1]} is assigned to GPU {assigned}; GPU {gpu} did not start this model.', flush=True)
        sys.exit(75)
occupants = subprocess.check_output(
    ['nvidia-smi', f'--id={gpu}', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
if occupants:
    print(f'GPU {gpu} is occupied by PID(s) {occupants}; inference was not started.', flush=True)
    sys.exit(75)

import torch

root = Path('/mnt/sv0/sean')
project = root / 'Ludens'
out = args.out_dir.resolve()
out.mkdir(parents=True, exist_ok=True)
image_path = args.image.resolve()
prompt = (args.prompt_file or out / 'character_echo.prompt.txt').read_text()
output = out / f'{args.model}_character.mp4'
started = perf_counter()
inference_seconds = None

match args.model:
    case 'wan_s2v':
        from math import ceil
        import soundfile as sf

        repo = root / 'wm_repos/Wan2.2'
        sys.path.insert(0, str(repo))
        from wan import WanS2V
        from wan.configs import WAN_CONFIGS
        from diffusers.utils import export_to_video

        torch.set_num_threads(4)
        config = WAN_CONFIGS['s2v-14B']
        pipe = WanS2V(config, str(root / 'models/Wan2.2-S2V-14B'), device_id=0,
                      convert_model_dtype=True)
        inference_started = perf_counter()
        video = pipe.generate(input_prompt=' '.join(prompt.split()), ref_image_path=str(image_path),
                              audio_path=str(args.audio.resolve()), max_area=1280 * 704,
                              enable_tts=False, tts_prompt_audio=None, tts_prompt_text=None, tts_text=None,
                              num_repeat=None, infer_frames=80, sampling_steps=config.sample_steps,
                              guide_scale=config.sample_guide_scale, shift=config.sample_shift,
                              seed=7, offload_model=True, init_first_frame=True)
        torch.cuda.synchronize()
        details = dict(inference_seconds=perf_counter() - inference_started, fps=config.sample_fps,
                       frames=int(video.shape[1]), audio=str(args.audio.resolve()), image=str(image_path),
                       steps=config.sample_steps, audio_conditioning=True)
        frames = video.clamp(-1, 1).add(1).div(2).permute(1, 2, 3, 0).float().cpu().numpy()
        silent = out / 'wan_s2v_silent.mp4'
        export_to_video(frames, str(silent), fps=config.sample_fps)
        audio_seconds = sf.info(str(args.audio.resolve())).duration
        output_frames = min(len(frames), ceil(audio_seconds * config.sample_fps))
        subprocess.run([str(project / 'research/out/video_quality_20260922/bin/ffmpeg'), '-nostdin',
                        '-v', 'error', '-i', str(silent), '-i', str(args.audio.resolve()),
                        '-map', '0:v:0', '-map', '1:a:0', '-t', str(output_frames / config.sample_fps),
                        '-c:v', 'libx264', '-threads', '4', '-crf', '18', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-movflags', '+faststart', str(output)], check=True)
        details.update(audio_seconds=audio_seconds, output_frames=output_frames)
        (out / 'speech_conditioning.json').write_text(json.dumps(details, indent=2))
    case 'echo_flash':
        repo = root / 'wm_repos/JoyAI-Echo/echo_wm'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ['inference_wm_causal.py', '--image', str(image_path), '--prompt', prompt,
                    '--action-str', 'none-120', '--checkpoint', str(root / 'models/Echo-WM/echo-wm-flash.safetensors'),
                    '--gemma-path', str(root / 'models/gemma-3-12b-it-qat-q4_0-unquantized'),
                    '--width', '1280', '--height', '704', '--num-frames', '121', '--fps', '24',
                    '--fov-deg', '70', '--seed', '7', '--no-action-overlay', '--output', str(output)]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
    case 'joy':
        request = json.loads((project / 'research/out/video_quality_20260922/joy_character.json').read_text())
        request.update(condition_img=str(image_path), prompt=prompt)
        (out / 'joy_character.json').write_text(json.dumps(request, ensure_ascii=False, indent=2))
        repo = root / 'wm_repos/JoyAI-Echo/echo_longvideo'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ['inference.py', '--config', str(repo / 'configs/inference.smoke_bf16.yaml'),
                    '--request', str(out / 'joy_character.json'), '--output-root', str(out / 'joy'),
                    '--video-fps', '24', '--seed', '7']
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
        videos = list((out / 'joy/seed7-quality/joy_character').glob('inference_*/result.mp4'))
        if len(videos) != 1:
            raise ValueError(f'Expected one Joy output, found {videos}')
        shutil.copyfile(videos[0], output)
    case 'ltx_full' | 'ltx_distilled':
        from diffusers import FlowMatchEulerDiscreteScheduler, LTX2ImageToVideoPipeline, LTX2VideoTransformer3DModel
        from diffusers.pipelines.ltx2.utils import DEFAULT_NEGATIVE_PROMPT, DISTILLED_SIGMA_VALUES
        from diffusers.utils import encode_video
        from PIL import Image

        path = root / 'models/LTX-2.5-Diffusers'
        components = {}
        if args.model == 'ltx_full':
            components['transformer'] = LTX2VideoTransformer3DModel.from_pretrained(
                path, subfolder='transformer_full', torch_dtype=torch.bfloat16)
        pipe = LTX2ImageToVideoPipeline.from_pretrained(path, torch_dtype=torch.bfloat16, **components)
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        options = {'num_inference_steps': 30}
        if args.model == 'ltx_full':
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(
                pipe.scheduler.config, use_dynamic_shifting=True, shift_terminal=0.1)
        else:
            options = dict(sigmas=DISTILLED_SIGMA_VALUES, guidance_scale=1.0, audio_guidance_scale=1.0,
                           stg_scale=0.0, audio_stg_scale=0.0, modality_scale=1.0, audio_modality_scale=1.0)
        torch.cuda.synchronize()
        inference_started = perf_counter()
        video, audio = pipe(image=Image.open(image_path).convert('RGB'), prompt=' '.join(prompt.split()),
                            negative_prompt=DEFAULT_NEGATIVE_PROMPT + ', subtitles, captions, on-screen text',
                            width=1280, height=704, num_frames=args.num_frames, frame_rate=args.fps,
                            generator=torch.Generator('cuda').manual_seed(args.seed), output_type='np',
                            return_dict=False, **options)
        torch.cuda.synchronize()
        inference_seconds = perf_counter() - inference_started
        encode_video(video[0], fps=args.fps, output_path=str(output), audio=audio[0].float().cpu(),
                     audio_sample_rate=pipe.vocoder.config.output_sampling_rate)
    case 'minimax':
        from diffusers import ComponentsManager, ModularPipeline
        from diffusers.utils import encode_video
        from PIL import Image

        path = root / 'models/MiniMax-H3'
        components = ComponentsManager()
        pipe = ModularPipeline.from_pretrained(str(path), workflow='fl2va', components_manager=components)
        pipe.load_components(pretrained_model_name_or_path=str(path), torch_dtype=torch.bfloat16)
        components.enable_auto_cpu_offload(device='cuda:0', memory_reserve_margin='10GB')
        torch.cuda.synchronize()
        inference_started = perf_counter()
        result = pipe(prompt=' '.join(prompt.split()), image=Image.open(image_path).convert('RGB'),
                      **(dict(width=args.width, height=args.height) if args.width is not None else {}),
                      num_frames=124, num_inference_steps=50, generator=torch.Generator('cuda').manual_seed(7),
                      output_type='np', output=['videos', 'audio', 'sampling_rate'])
        torch.cuda.synchronize()
        inference_seconds = perf_counter() - inference_started
        encode_video(result['videos'][0], fps=24, output_path=str(output),
                     audio=result['audio'][0].float().cpu(), audio_sample_rate=result['sampling_rate'])
    case 'dreamx':
        repo = root / 'wm_repos/DreamX-World'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        dataset = [dict(image_path=str(image_path), caption=prompt, action_seq=[''],
                        action_speed_list=[1], task_id='character')]
        data_path = out / 'dreamx_character.json'
        data_path.write_text(json.dumps(dataset, ensure_ascii=False))
        sys.argv = ['inference_ar_forcing.py', '--config_path', 'configs/dreamx-ar/causal_camera_forcing_5b.yaml',
                    '--model_name', str(root / 'models/Wan2.2-TI2V-5B'),
                    '--transformer_path', str(repo / 'configs/dreamx-ar'),
                    '--base_checkpoint_path', str(root / 'models/DreamX-World-5B/model.safetensors'),
                    '--data_path', str(data_path), '--output_folder', str(out / 'dreamx'),
                    '--num_output_frames', '21', '--fps', '16', '--seed', '7',
                    '--color_correction_strength', '1.0', '--chunk_relative']
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
        shutil.copyfile(out / 'dreamx/character_opening_opening_tavern_seed7_v1.mp4', output)
    case 'matrix':
        repo = root / 'wm_repos/Matrix-Game/Matrix-Game-2'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ['inference.py', '--config_path', 'configs/inference_yaml/inference_universal.yaml',
                    '--checkpoint_path', str(root / 'models/Matrix-Game-2.0/base_distilled_model/base_distill.safetensors'),
                    '--img_path', str(image_path), '--output_folder', str(out / 'matrix'),
                    '--num_output_frames', '21', '--seed', '7',
                    '--pretrained_model_path', str(root / 'models/Matrix-Game-2.0')]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
        shutil.copyfile(out / 'matrix/demo.mp4', output)
    case 'wan':
        repo = root / 'wm_repos/Wan2.2'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ['generate.py', '--task', 'ti2v-5B', '--size', '1280*704',
                    '--ckpt_dir', str(root / 'models/Wan2.2-TI2V-5B'), '--image', str(image_path),
                    '--prompt', prompt, '--frame_num', '121', '--sample_steps', '50',
                    '--base_seed', '7', '--offload_model', 'True', '--convert_model_dtype',
                    '--save_file', str(output)]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
    case 'lingbot':
        repo = root / 'wm_repos/lingbot-world-v2'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ['generate.py', '--task', 'i2v-1.3B', '--size', '832*480',
                    '--ckpt_dir', str(root / 'models/lingbot-world-v2-1.3b-causal-fast'),
                    '--image', str(image_path), '--prompt', prompt, '--action_path', str(out / 'lingbot_camera'),
                    '--frame_num', '121', '--base_seed', '7', '--ulysses_size', '1',
                    '--local_attn_size', '18', '--sink_size', '6', '--convert_model_dtype',
                    '--offload_model', 'True', '--save_file', str(output)]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
    case 'liveavatar':
        repo = root / 'wm_repos/LiveAvatar'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        os.environ.update(RANK='0', LOCAL_RANK='0', WORLD_SIZE='1', MASTER_ADDR='127.0.0.1',
                          MASTER_PORT='29833', ENABLE_COMPILE='false')
        sys.argv = ['minimal_inference/s2v_streaming_interact.py', '--ulysses_size', '1',
                    '--task', 's2v-14B', '--size', '1280*720', '--base_seed', '7',
                    '--training_config', 'liveavatar/configs/s2v_causal_sft.yaml',
                    '--offload_model', 'True', '--convert_model_dtype', '--prompt', prompt,
                    '--image', str(image_path), '--audio', str(out.parent / 'character_180_20260922/character_flash.wav'),
                    '--infer_frames', '48', '--load_lora', '--lora_path_dmd', str(root / 'models/Live-Avatar/liveavatar.safetensors'),
                    '--sample_steps', '4', '--sample_guide_scale', '0', '--num_clip', '3',
                    '--num_gpus_dit', '1', '--sample_solver', 'euler', '--single_gpu', '--offload_kv_cache',
                    '--ckpt_dir', str(root / 'models/Wan2.2-S2V-14B'), '--save_file', str(output)]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
    case 'hallo' | 'hallo_t2v':
        repo = root / 'wm_repos/Hallo-Live'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        is_image = args.model == 'hallo'
        sys.argv = ['inference.py', '--config_path', str(out / ('hallo_config.yaml' if is_image else 'hallo_t2v_config.yaml')),
                    '--model_dir', str(root / 'models'), '--generator_ckpt', str(root / 'models/Hallo-Live/hallolive_dit.pt'),
                    '--data_path', str(out / ('hallo_inputs' if is_image else 'hallo_t2v.csv')),
                    '--output_folder', str(out / args.model),
                    '--use_ema', '--num_output_frames', '31' if is_image else '30', '--seed', '7']
        if is_image:
            sys.argv.append('--i2v')
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
        videos = [p for p in (out / args.model).glob('*.mp4') if not p.name.endswith('.silent.mp4')]
        if len(videos) != 1:
            raise ValueError(f'Expected one Hallo output, found {videos}')
        shutil.copyfile(videos[0], output)
    case 'flashhead':
        repo = root / 'wm_repos/SoulX-FlashHead'
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        import flash_head.src.pipeline.flash_head_pipeline as portrait
        portrait.COMPILE_MODEL = False
        portrait.COMPILE_VAE = False
        portrait.USE_PARALLEL_VAE = False
        sys.argv = ['generate_video.py', '--ckpt_dir', str(root / 'models/SoulX-FlashHead-1_3B'),
                    '--wav2vec_dir', str(root / 'models/wav2vec2-base-960h'), '--model_type', 'pro',
                    '--cond_image', str(out / 'portrait_reference.png'),
                    '--audio_path', str(out.parent / 'character_180_20260922/character_flash.wav'),
                    '--audio_encode_mode', 'stream', '--base_seed', '7', '--save_file', str(output)]
        runpy.run_path(str(repo / sys.argv[0]), run_name='__main__')
    case _:
        raise ValueError(f'Unknown model: {args.model}')

torch.cuda.synchronize()
metrics = dict(model=args.model, torch=torch.__version__, seconds=perf_counter() - started,
               peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30, output=str(output))
if args.width is not None:
    metrics.update(width=args.width, height=args.height)
if inference_seconds is not None:
    metrics.update(inference_seconds=inference_seconds, fps=args.fps,
                   num_frames=124 if args.model == 'minimax' else args.num_frames, seed=args.seed)
(out / f'{args.model}_metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
print(json.dumps(metrics), flush=True)
