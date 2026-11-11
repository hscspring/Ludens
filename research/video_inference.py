import json
import sys
from pathlib import Path
from time import perf_counter

import torch
from PIL import Image


class VideoInference:
    def __init__(self, profile: str, width: int, height: int, seed: int) -> None:
        self.profile = profile
        self.width = width
        self.height = height
        self.seed = seed
        self.root = Path('/mnt/sv0/sean')
        self.details = dict(profile=profile, width=width, height=height, fps=24)
        started = perf_counter()
        match profile:
            case 'minimax_base' | 'minimax_turbo8':
                from diffusers import ComponentsManager, ModularPipeline

                path = self.root / 'models/MiniMax-H3'
                self.components = ComponentsManager()
                self.pipe = ModularPipeline.from_pretrained(
                    str(path), workflow='fl2va', components_manager=self.components)
                self.pipe.load_components(pretrained_model_name_or_path=str(path), torch_dtype=torch.bfloat16)
                if profile == 'minimax_turbo8':
                    sys.path.insert(0, str(self.root / 'Ludens/research/out/acceleration_20260924/upstream'))
                    from inference_minimax_h3 import load_lora_adapter

                    lora = self.root / 'models/MiniMax-H3-Turbo/minimax_h3_fl2v_turbo_8step_v1.0_bf16.safetensors'
                    load_lora_adapter(self.pipe.transformer, lora, lora_alpha=8, lora_scale=1.0, fuse_lora=True)
                    self.pipe.scheduler.set_shift(12)
                    self.pipe.audio_scheduler.set_shift(3)
                    self.details.update(lora=str(lora), lora_alpha=8, video_shift=12, audio_shift=3)
                self.components.enable_auto_cpu_offload(device='cuda:0', memory_reserve_margin='10GB')
                self.details.update(nfe=8 if profile == 'minimax_turbo8' else 49, num_frames=124,
                                    backend='diffusers / BF16 / auto CPU offload')
            case 'ltx_bf16' | 'ltx_fp8':
                from diffusers import LTX2ImageToVideoPipeline

                self.pipe = LTX2ImageToVideoPipeline.from_pretrained(
                    self.root / 'models/LTX-2.5-Diffusers', torch_dtype=torch.bfloat16)
                if profile == 'ltx_fp8':
                    from torchao.quantization import Float8Tensor
                    from torchao.quantization import Float8DynamicActivationFloat8WeightConfig, quantize_

                    self.pipe.transformer.to('cuda')
                    quantize_(self.pipe.transformer, Float8DynamicActivationFloat8WeightConfig())
                    count = sum(isinstance(getattr(module, 'weight', None), Float8Tensor)
                                for module in self.pipe.transformer.modules())
                    if count == 0:
                        raise RuntimeError('LTX FP8 did not quantize any weight')
                    self.details['quantized_modules'] = count
                    self.pipe.transformer.to('cpu')
                    torch.cuda.empty_cache()
                self.pipe.enable_model_cpu_offload()
                self.pipe.vae.enable_tiling()
                self.details.update(num_frames=121, nfe=8, backend='torchao dynamic FP8' if profile == 'ltx_fp8' else 'BF16',
                                    attention='PyTorch SDPA', offload='model CPU offload')
            case 'joy_bf16' | 'joy_fp8':
                repo = self.root / 'wm_repos/JoyAI-Echo/echo_longvideo'
                sys.path.insert(0, str(repo))
                from inference import InferenceConfig, InferenceEngine

                checkpoint = 'echo15_fp8' if profile == 'joy_fp8' else 'echo15_full_dmd'
                config = InferenceConfig(repo / 'configs/inference.smoke_bf16.yaml',
                                         checkpoint=str(self.root / 'models/JoyAI-Echo' / checkpoint),
                                         video_fps=24, video_width=width, video_height=height)
                self.pipe = InferenceEngine(config)
                self.pipe.load_generator()
                self.details.update(num_frames=121, nfe=8, backend=self.pipe.generator_load_report.backend,
                                    conditioning='re-encode current frame each turn; generator retained in RAM',
                                    memory_slots=0)
            case _:
                raise ValueError(f'Unknown inference profile: {profile}')
        torch.cuda.synchronize()
        self.load_seconds = perf_counter() - started

    def __call__(self, reference: Path, prompt: str, out: Path, last_image: Path | None = None) -> dict:
        if last_image is not None and not self.profile.startswith('minimax_'):
            raise ValueError('End-frame conditioning is only connected for MiniMax')
        torch.cuda.reset_peak_memory_stats()
        started = perf_counter()
        output = out / f'{self.profile}_character.mp4'
        with torch.inference_mode():
            if self.profile.startswith('joy_'):
                timings = self._joy(reference, prompt, out, output)
            else:
                timings = self._diffusers(reference, prompt, output, last_image)
        torch.cuda.synchronize()
        metrics = dict(self.details, **timings, response_seconds=perf_counter() - started,
                       load_seconds=self.load_seconds, peak_allocated_gib=torch.cuda.max_memory_allocated() / 2**30)
        metrics.update(seed=self.seed, last_image=str(last_image) if last_image is not None else None)
        (out / f'{self.profile}_metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
        return metrics

    def _diffusers(self, reference: Path, prompt: str, output: Path, last_image: Path | None = None) -> dict:
        from diffusers.utils import encode_video

        started = perf_counter()
        options = dict(image=Image.open(reference).convert('RGB'), prompt=' '.join(prompt.split()),
                       width=self.width, height=self.height, num_frames=self.details['num_frames'],
                       generator=torch.Generator('cuda').manual_seed(self.seed), output_type='np')
        if self.profile.startswith('minimax_'):
            if last_image is not None:
                options['last_image'] = Image.open(last_image).convert('RGB')
            # H3 counts sigma grid points, including terminal zero: 9 points = 8 forwards.
            result = self.pipe(**options, num_inference_steps=9 if self.profile == 'minimax_turbo8' else 50,
                               output=['videos', 'audio', 'sampling_rate'])
            video, audio, rate = result['videos'][0], result['audio'][0], result['sampling_rate']
        else:
            from diffusers.pipelines.ltx2.utils import DEFAULT_NEGATIVE_PROMPT, DISTILLED_SIGMA_VALUES

            video, audio = self.pipe(**options, sigmas=DISTILLED_SIGMA_VALUES, frame_rate=24,
                                     negative_prompt=DEFAULT_NEGATIVE_PROMPT + ', subtitles, captions, on-screen text',
                                     guidance_scale=1.0, audio_guidance_scale=1.0, stg_scale=0.0,
                                     audio_stg_scale=0.0, modality_scale=1.0, audio_modality_scale=1.0,
                                     return_dict=False)
            video, audio, rate = video[0], audio[0], self.pipe.vocoder.config.output_sampling_rate
        torch.cuda.synchronize()
        seconds = perf_counter() - started
        encode_video(video, fps=24, output_path=str(output), audio=audio.float().cpu(), audio_sample_rate=rate)
        return dict(inference_seconds=seconds)

    def _joy(self, reference: Path, prompt: str, out: Path, output: Path) -> dict:
        from r2v_schema import load_r2v_request

        request_file = out / 'request.json'
        request_file.write_text(json.dumps(dict(work_id='acceleration', shot_id=out.name, prompt=prompt,
                                               condition_img=str(reference), memory_slots=[], num_frames=121,
                                               width=self.width, height=self.height, seed=self.seed,
                                               duration_sec=121 / 24), ensure_ascii=False))
        request = load_r2v_request(request_file)
        self.pipe.stage_generator_for_conditioning('cpu')
        started = perf_counter()
        bundles = self.pipe.prepare_conditions([request_file], [request])
        condition_seconds = perf_counter() - started
        result = self.pipe.run_request(request_file, request, out, bundles[request_file])
        Path(result['output_path']).rename(output)
        return dict(condition_seconds=condition_seconds, joy_native_timing=result['metadata']['timing'],
                    inference_seconds=None)
