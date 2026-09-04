"""录制轨迹 → 视觉链 smoke：读一个 session 的 state_history.jsonl，相邻 state
驱动 Kontext create/edit（可选 LTX animate），落盘帧/clip + index.html 供肉眼验证
"场景跟着剧情变 + 角色/场景保持一致"。

    python replay.py --session run_davr/demo/sessions/771abfe3811a --out out/771
    python replay.py --session ... --animate 3      # 前 3 帧另出 LTX 动态

renderers 进程内直接调用（同 env），不走 HTTP；HTTP 服务留到接 serve_demo 时再写。
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from scene_state import motion_hint, replay_plan


def load_states(session: Path) -> list[dict]:
    lines = (session / "state_history.jsonl").read_text().splitlines()
    return [json.loads(ln)["state"] for ln in lines if ln.strip()]


def write_index(out: Path, frames: list[dict]) -> None:
    cards = []
    for f in frames:
        loc = html.escape(str(f["state"].get("location")))
        reason = html.escape(f["reason"])
        clip = (
            f'<video src="{f["clip"]}" controls loop muted width="480"></video>'
            if f.get("clip")
            else ""
        )
        cards.append(
            f'<div class="card"><div class="meta">#{f["idx"]} · {f["op"]} · {loc}</div>'
            f'<img src="{f["image"]}" width="480">{clip}'
            f'<div class="reason">{reason}</div></div>'
        )
    doc = (
        "<!doctype html><meta charset=utf-8><title>scene replay</title>"
        "<style>body{background:#111;color:#ddd;font:14px system-ui;margin:24px}"
        ".card{margin:0 0 32px;max-width:520px}.meta{color:#8bd;margin-bottom:6px}"
        "img,video{border-radius:8px;display:block;margin-bottom:6px}"
        ".reason{color:#999;font-size:12px}</style>"
        "<h2>scene replay</h2>" + "".join(cards)
    )
    (out / "index.html").write_text(doc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--renderer", choices=["klein", "kontext"], default="klein")
    ap.add_argument("--flux2-model", default="/mnt/local/sean/models/FLUX.2-klein-4B")
    ap.add_argument("--kontext-model", default="/mnt/local/sean/models/FLUX.1-Kontext-dev")
    ap.add_argument("--ltx-model", default="/mnt/local/sean/models/LTX-2.5-Diffusers")
    ap.add_argument("--render-device", default="cuda:0")
    ap.add_argument("--ltx-device", default="cuda:1")
    ap.add_argument("--size", default="1024x1024", help="WxH，需 %16(klein)/%32(喂 LTX)")
    ap.add_argument("--animate", type=int, default=0, help="给前 N 个渲染帧另出 LTX 动态 clip")
    ap.add_argument("--max-frames", type=int, default=40, help="上限，防止一次 smoke 出太多帧")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    from renderers import Flux2Renderer, KontextRenderer  # 延迟 import，纯逻辑失败时不必载 torch

    args.out.mkdir(parents=True, exist_ok=True)
    states = load_states(args.session)
    plan = replay_plan(states)[: args.max_frames]
    print(f"{len(states)} snapshots -> {len(plan)} frames (cap {args.max_frames})")

    size = tuple(int(x) for x in args.size.lower().split("x"))
    if args.renderer == "klein":
        renderer = Flux2Renderer(args.flux2_model, device=args.render_device, size=size)
    else:
        renderer = KontextRenderer(args.kontext_model, device=args.render_device, size=size)
    prev_image = None
    for f in plan:
        if f["op"] == "create":
            image = renderer.create(f["reason"], seed=args.seed)
        else:
            image = renderer.edit(prev_image, f["reason"], seed=args.seed)
        name = f"frame_{f['idx']:04d}.png"
        image.save(args.out / name)
        f["image"] = name
        prev_image = image
        print(f"  [{f['idx']:>4}] {f['op']} -> {name}")

    if args.animate > 0:
        from renderers import MotionRenderer

        motion = MotionRenderer(args.ltx_model, device=args.ltx_device)
        from PIL import Image

        for f in plan[: args.animate]:
            clip = f"clip_{f['idx']:04d}.mp4"
            motion.animate(Image.open(args.out / f["image"]), motion_hint(f["state"]), args.out / clip, seed=args.seed)
            f["clip"] = clip
            print(f"  [{f['idx']:>4}] animate -> {clip}")

    write_index(args.out, plan)
    print(f"done -> {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
