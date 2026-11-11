"""Tier 0 视觉渲染器：图像渲染器（默认 FLUX.2 klein，备选 FLUX.1 Kontext）+ LTX-2.5（图生视频）。

两个图像渲染器共享接口 create(prompt) / edit(prev, instruction)，同一 size 保证维度一致。
都只在 scene_service 专属 env 里跑（torch + diffusers-from-main）。
MotionRenderer 的接口刻意留成 animate(image, hint) -> mp4，后续可换成 HelixWorld。
"""

from __future__ import annotations

from pathlib import Path

import torch
from diffusers import Flux2KleinPipeline, FluxKontextPipeline, LTX2ImageToVideoPipeline
from diffusers.utils import export_to_video
from PIL import Image

LTX_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted"

# FLUX.2 klein-4B 蒸馏：官方 4 步、guidance=1.0（is_distilled 时 >1 会被忽略）
FLUX2_STEPS = 4
FLUX2_GUIDANCE = 1.0

# Kontext 采样：官方 edit 用 2.5；从中性画布 create 用更强的 3.5 压过底色
GUIDANCE_CREATE = 3.5
GUIDANCE_EDIT = 2.5
KONTEXT_STEPS = 28


class Flux2Renderer:
    def __init__(self, model_path: str, device: str = "cuda:0", size: tuple[int, int] = (1024, 1024)):
        self.device = device
        self.size = size  # (W, H)，需 %16==0（klein）且 %32==0（喂 LTX 不重采样）
        self.pipe = Flux2KleinPipeline.from_pretrained(model_path, torch_dtype=torch.bfloat16).to(device)

    def _gen(self, seed: int) -> torch.Generator:
        return torch.Generator(device=self.device).manual_seed(seed)

    def create(self, prompt: str, seed: int = 42) -> Image.Image:
        # klein 统一模型：无参考图即纯 t2i，不必再拉一个 t2i 底座
        return self.pipe(
            prompt=prompt,
            width=self.size[0],
            height=self.size[1],
            guidance_scale=FLUX2_GUIDANCE,
            num_inference_steps=FLUX2_STEPS,
            generator=self._gen(seed),
        ).images[0]

    def edit(self, prev_image: Image.Image, instruction: str, seed: int = 42,
             size: tuple[int, int] | None = None, identity: Image.Image | None = None) -> Image.Image:
        width, height = size or self.size
        return self.pipe(
            image=[prev_image, identity] if identity is not None else prev_image,
            prompt=instruction,
            width=width,
            height=height,
            guidance_scale=FLUX2_GUIDANCE,
            num_inference_steps=FLUX2_STEPS,
            generator=self._gen(seed),
        ).images[0]


class KontextRenderer:
    def __init__(self, model_path: str, device: str = "cuda:0", size: tuple[int, int] = (960, 544)):
        self.device = device
        self.size = size  # (W, H)，需 %16==0（Kontext）且 %32==0（喂 LTX 不重采样）
        self.pipe = FluxKontextPipeline.from_pretrained(model_path, torch_dtype=torch.bfloat16).to(device)
        self._neutral = Image.new("RGB", size, (127, 127, 127))

    def _gen(self, seed: int) -> torch.Generator:
        return torch.Generator(device=self.device).manual_seed(seed)

    def create(self, prompt: str, seed: int = 42) -> Image.Image:
        # 无上一帧 → 中性画布上编辑出整场景，避免再拉一个 t2i 底座
        return self.pipe(
            image=self._neutral,
            prompt=prompt,
            width=self.size[0],
            height=self.size[1],
            guidance_scale=GUIDANCE_CREATE,
            num_inference_steps=KONTEXT_STEPS,
            generator=self._gen(seed),
        ).images[0]

    def edit(self, prev_image: Image.Image, instruction: str, seed: int = 42) -> Image.Image:
        return self.pipe(
            image=prev_image,
            prompt=instruction,
            width=self.size[0],
            height=self.size[1],
            guidance_scale=GUIDANCE_EDIT,
            num_inference_steps=KONTEXT_STEPS,
            generator=self._gen(seed),
        ).images[0]


class MotionRenderer:
    def __init__(
        self,
        model_path: str,
        device: str = "cuda:1",
        num_frames: int = 121,
        fps: int = 24,
        size: tuple[int, int] = (768, 768),
    ):
        self.device = device
        self.num_frames = num_frames  # 必须 8k+1
        self.fps = fps
        self.size = size  # (W, H)，需 %32；1:1 对齐 klein 首帧
        self.pipe = LTX2ImageToVideoPipeline.from_pretrained(model_path, torch_dtype=torch.bfloat16)
        self.pipe.enable_model_cpu_offload(device=device)

    def animate(self, image: Image.Image, hint: str, out_path: str | Path, seed: int = 42) -> Path:
        out_path = Path(out_path)
        video, _audio = self.pipe(
            image=image,
            prompt=hint,
            negative_prompt=LTX_NEGATIVE,
            width=self.size[0],
            height=self.size[1],
            num_frames=self.num_frames,
            frame_rate=self.fps,
            generator=torch.Generator(device=self.device).manual_seed(seed),
            return_dict=False,
        )
        export_to_video(video[0], str(out_path), fps=self.fps)
        return out_path
