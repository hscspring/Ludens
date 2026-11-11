"""Tier 0 渲染服务（torch 只待在这里）：常驻 klein，POST /render {session_id, state}
→ 每会话一台 SceneState 决策 create/edit/none → 落盘 PNG → 返回图 URL + caption。

demo_server 经 HTTP 调它；渲染与 demo web 分进程，web 不背 torch。图片写到共享 --out，
由 demo_server 的 StaticFiles 对浏览器提供（同机同盘，无需再代理）。

    python render_server.py                 # cuda:0，klein@1024²，:8781
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import io
import logging
import threading
import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from scene_state import SceneState, caption

if TYPE_CHECKING:
    from renderers import Flux2Renderer

HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
SVC = None


class RenderReq(BaseModel):
    session_id: str
    state: dict


class EditReq(BaseModel):
    image: str
    instruction: str
    identity: str | None = None


class GenerateReq(BaseModel):
    prompt: str
    seed: int = 42


class SegmentReq(BaseModel):
    image: str
    boxes: list[list[float]]


class RenderService:
    def __init__(self, pipe: Flux2Renderer, root: Path) -> None:
        self.pipe = pipe
        self.root = root
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()
        from transformers import Sam2Model, Sam2Processor

        self.segmenter = Sam2Model.from_pretrained('/mnt/sv0/sean/models/sam2.1-hiera-tiny').to(pipe.device).eval()
        self.processor = Sam2Processor.from_pretrained('/mnt/sv0/sean/models/sam2.1-hiera-tiny')

    def generate(self, prompt: str, seed: int) -> bytes:
        with self.lock:
            image = self.pipe.create(prompt, seed=seed)
        output = io.BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def segment(self, encoded: str, boxes: list[list[float]]) -> dict:
        import torch

        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as source:
            image = source.convert('RGB')
        inputs = self.processor(images=image, input_boxes=[boxes], return_tensors='pt').to(self.pipe.device)
        with self.lock, torch.inference_mode():
            result = self.segmenter(**inputs, multimask_output=False)
        masks = self.processor.post_process_masks(result.pred_masks.cpu(), inputs['original_sizes'].cpu())[0]
        encoded_masks = []
        for mask in masks:
            buffer = io.BytesIO()
            Image.fromarray((mask[0].numpy() > 0).astype('uint8') * 255).save(buffer, format='PNG')
            encoded_masks.append(base64.b64encode(buffer.getvalue()).decode())
        return {'masks': encoded_masks}

    def render(self, sid: str, state: dict) -> dict:
        with self.lock:
            s = self.sessions.setdefault(sid, {"scene": SceneState(), "prev": None, "n": 0})
            plan = s["scene"].step(state)
            if plan is None:
                return {"op": "none"}
            op, reason = plan
            image = self.pipe.create(reason) if op == "create" else self.pipe.edit(s["prev"], reason)
            s["prev"] = image
            name = f"{s['n']:04d}.png"
            s["n"] += 1
            (self.root / sid).mkdir(parents=True, exist_ok=True)
            image.save(self.root / sid / name)
            return {"op": op, "url": f"/scenes/{sid}/{name}", "caption": caption(state)}

    def edit(self, encoded: str, instruction: str, identity: str | None = None) -> bytes:
        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as source:
            image = source.convert("RGB")
        identity_image = None
        if identity is not None:
            with Image.open(io.BytesIO(base64.b64decode(identity, validate=True))) as source:
                identity_image = source.convert("RGB")
        if image.width % 16 or image.height % 16:
            raise ValueError("Reference dimensions must be multiples of 16")
        with self.lock:
            edited = self.pipe.edit(image, instruction, size=image.size, identity=identity_image)
        output = io.BytesIO()
        edited.save(output, format="PNG")
        return output.getvalue()


@app.post("/render")
async def render(req: RenderReq):
    return await asyncio.to_thread(SVC.render, req.session_id, req.state)


@app.post("/edit")
def edit(req: EditReq) -> Response:
    try:
        return Response(SVC.edit(req.image, req.instruction, req.identity), media_type="image/png")
    except (ValueError, binascii.Error, OSError, RuntimeError) as exc:
        logging.getLogger(__name__).error("Image edit failed: %s", exc)
        raise HTTPException(502, "Image edit failed") from exc


@app.post('/generate')
def generate(req: GenerateReq) -> Response:
    return Response(SVC.generate(req.prompt, req.seed), media_type='image/png')


@app.post('/segment')
def segment(req: SegmentReq) -> dict:
    return SVC.segment(req.image, req.boxes)


@app.get('/health')
def health() -> dict:
    return {'ready': SVC is not None, 'identity_reference': True}


def main():
    global SVC
    ap = argparse.ArgumentParser()
    ap.add_argument("--flux2-model", default="/mnt/sv0/sean/models/FLUX.2-klein-4B")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--size", default="1024x1024", help="WxH，宽高须为16的倍数")
    ap.add_argument("--out", default=os.path.join(HERE, "out/live"))
    ap.add_argument("--port", type=int, default=8781)
    args = ap.parse_args()

    from renderers import Flux2Renderer  # 延迟 import：torch 只在真正起服务时加载

    size = tuple(int(x) for x in args.size.lower().split("x"))
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    SVC = RenderService(Flux2Renderer(args.flux2_model, device=args.device, size=size), root)
    print(f"[render] klein {args.flux2_model} on {args.device} @ {size} → {root}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
