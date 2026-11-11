"""离线出 Ludens 开场图:FLUX.1-Kontext 拿参考图锁 Cassian 外形,竖屏参考 → 宽屏电影感开场,单主体治幽灵人。

纯出图看效果,不接管线;效果 OK 后再把成图当开场首拍的 condition_img 首帧(那步改 ShotRenderer/StoryFeed)。
env: scene_service(diffusers 0.41)。
"""
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Sean 09-17 放行 0-1,nvidia-smi 确认 0 空;4~7 是训练,勿碰

from pathlib import Path

import torch
from diffusers import FluxKontextPipeline
from diffusers.utils import load_image

MODEL = "/mnt/sv0/sean/models/FLUX.1-Kontext-dev"
REF = "/mnt/sv0/sean/Ludens/research/assets/anchor_hero.png"
OUT_DIR = "/mnt/sv0/sean/Ludens/research/out/opening"

PROMPT = (  # 暖调+单人+外形+居中 前置进 CLIP 77 token;氛围细节靠后交给 T5(无 77 限制)
    "Warm amber skin tones, teal-and-amber cinematic film grade, soft cool shadows, "
    "centered composition, semi-realistic painterly anime. A single blond man, Cassian "
    "— amber eyes, dark coat, a cigarette in his hand — centered in frame, leaning against "
    "a weathered brick wall in a dark alley behind a bar, past midnight, a soft warm practical "
    "light glowing on the wall, lifting his gaze to the viewer. Only one person, no other people. "
    "Cinematic wide horizontal shot, volumetric lighting, highly detailed skin, filmic contrast, "
    "atmospheric depth. No subtitles or text."
)

WIDTH, HEIGHT = 1344, 768  # FLUX Kontext 原生 bucket,免尺寸调整警告(size 无所谓,Sean 09-09)
SEEDS = [42, 7, 123, 888]  # 多 seed 各出一张,挑最好的
GUIDANCE = 2.5
STEPS = 28


class KontextGenerator:
    def __init__(self, model_path: str = MODEL):
        self.pipe = FluxKontextPipeline.from_pretrained(model_path, torch_dtype=torch.bfloat16)
        self.pipe.to("cuda")

    def generate(self, ref_path: str, prompt: str, out_path: str, width: int, height: int,
                 seed: int, guidance_scale: float, steps: int) -> str:
        image = self.pipe(
            image=load_image(ref_path),
            prompt=prompt,
            width=width,
            height=height,
            guidance_scale=guidance_scale,
            num_inference_steps=steps,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path)
        return out_path


def main() -> None:
    gen = KontextGenerator()
    for seed in SEEDS:
        out = f"{OUT_DIR}/opening_seed{seed}.png"
        gen.generate(REF, PROMPT, out, WIDTH, HEIGHT, seed, GUIDANCE, STEPS)
        print(f"[opening] saved -> {out}  ({WIDTH}x{HEIGHT}, seed={seed}, guidance={GUIDANCE}, steps={STEPS})")


if __name__ == "__main__":
    main()
