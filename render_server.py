"""Tier 0 渲染服务（torch 只待在这里）：常驻 klein，POST /render {session_id, state}
→ 每会话一台 SceneState 决策 create/edit/none → 落盘 PNG → 返回图 URL + caption。

demo_server 经 HTTP 调它；渲染与 demo web 分进程，web 不背 torch。图片写到共享 --out，
由 demo_server 的 StaticFiles 对浏览器提供（同机同盘，无需再代理）。

    python render_server.py                 # cuda:0，klein@1024²，:8781
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from scene_state import SceneState, caption

HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI()
SVC = None


class RenderReq(BaseModel):
    session_id: str
    state: dict


class RenderService:
    def __init__(self, pipe, root: Path):
        self.pipe = pipe
        self.root = root
        self.sessions: dict[str, dict] = {}

    def render(self, sid: str, state: dict) -> dict:
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


@app.post("/render")
async def render(req: RenderReq):
    return await asyncio.to_thread(SVC.render, req.session_id, req.state)


def main():
    global SVC
    ap = argparse.ArgumentParser()
    ap.add_argument("--flux2-model", default="/mnt/local/sean/models/FLUX.2-klein-4B")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--size", default="1024x1024", help="WxH，需 %16(klein)")
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
