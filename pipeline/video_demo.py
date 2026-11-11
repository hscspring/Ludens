"""LudensPipeline:在线·自动单故事编排器 + web 播放层(同进程)。

玩家输入 → input_q → StoryFeed(产下一拍 request)→ request_q → ClipFactory(出片)→ ready_q → web 播放。
两个后台线程 + FastAPI;回合制:开场自动产第一拍,之后每拍播完停在末帧、开放输入框,玩家打一句话/一个动作
→ POST /api/act 驱动产下一拍 → 生成好切入播放。这是"第一人称·我改变世界"的最小闭环——{{user}} 不出镜,输入即驱动。
main() 只实例化 + 启动。
"""
from __future__ import annotations

import json
import os
import queue
import threading
from html import escape

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

from pipeline.joyai_clip_factory import JoyAIClipFactory
from pipeline.story_feed import StoryFeed

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Ludens 根
LIVE_DIR = os.path.join(HERE, "research", "out", "live")
PLACEHOLDER = os.path.join(HERE, "research", "out", "subbed", "shot_001.mp4")
CARDS = os.path.join(HERE, "seed_cards.json")
Q_MAX = 6            # 队列放深:生成端可多跑几片存着,某片偶发慢一拍时播放端有存货顶着不饿死


class LudensPipeline:
    def __init__(self, card: dict, clip_factory, live_dir: str = LIVE_DIR):
        self.feed = StoryFeed(card)
        self.player_intro = card.get("player_intro", "")
        self.action_example = card.get("action_example", "你说 / 你做什么…")
        self.factory = clip_factory
        self.live_dir = live_dir
        self.input_q: queue.Queue = queue.Queue(maxsize=4)  # 玩家输入:回合制,浅队列够
        self.request_q: queue.Queue = queue.Queue(maxsize=Q_MAX)
        self.ready_q: queue.Queue = queue.Queue(maxsize=Q_MAX)
        self.stop = threading.Event()
        os.makedirs(live_dir, exist_ok=True)
        self.app = self._build_app()

    def start_workers(self) -> None:
        threading.Thread(target=self.feed.run, args=(self.input_q, self.request_q, self.stop), daemon=True).start()
        threading.Thread(target=self.factory.run, args=(self.request_q, self.ready_q, self.stop), daemon=True).start()

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/", response_class=HTMLResponse)
        def index() -> str:
            page = INDEX_HTML.replace("__SCENE_INTRO__", escape(self.player_intro))
            page = page.replace("__ACTION_EXAMPLE__", escape(self.action_example, quote=True))
            return page if self.feed.opening_image else page.replace('poster="/cover"', '')

        @app.get("/cover")
        def cover() -> FileResponse:
            return FileResponse(self.feed.opening_image, media_type="image/png")

        @app.get("/api/next")
        def next_clip() -> dict:
            clip = self.ready_q.get()  # 阻塞直到有片:前端按播放节奏拉,天然节流
            return {"index": clip.index, "clip_url": f"/clips/shot_{clip.index:03d}.mp4", "said": clip.said}

        @app.post("/api/act")
        def act(inp: dict) -> dict:
            self.input_q.put(inp.get("text", ""))  # 玩家这拍输入 → 驱动 feed 产下一拍
            return {"ok": True}

        @app.get("/clips/{name}")
        def clip(name: str) -> FileResponse:
            return FileResponse(os.path.join(self.live_dir, os.path.basename(name)), media_type="video/mp4")

        return app

    def serve(self, host: str = "0.0.0.0", port: int = 8790) -> None:
        self.start_workers()
        uvicorn.run(self.app, host=host, port=port)


INDEX_HTML = """<!doctype html><html><head><meta charset=utf-8><title>Ludens</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
  html,body{margin:0;height:100%;background:#000;overflow:hidden;font-family:sans-serif}
  video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000}
  #hint{position:absolute;left:0;right:0;bottom:84px;text-align:center;color:#eee;font-size:15px;
        padding:0 16px;z-index:3;text-shadow:0 1px 4px #000;pointer-events:none}
  #bar{position:absolute;left:0;right:0;bottom:0;padding:16px;display:none;gap:10px;
       background:linear-gradient(transparent,rgba(0,0,0,.8));z-index:3}
  #bar.on{display:flex}
  #act{flex:1;padding:14px 16px;font-size:17px;border:0;border-radius:10px;
       background:rgba(255,255,255,.96);color:#111;outline:none}
  #go{padding:14px 22px;font-size:17px;border:0;border-radius:10px;background:#e6437a;color:#fff;cursor:pointer}
  #overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
           flex-direction:column;color:#fff;font-size:22px;cursor:pointer;background:rgba(0,0,0,.2);text-shadow:0 2px 8px #000;z-index:4}
  #intro{max-width:640px;padding:20px;font-size:17px;line-height:1.7;background:rgba(0,0,0,.65);border-radius:12px}
</style></head><body>
<video id=v playsinline poster="/cover"></video>
<div id=hint></div>
<div id=bar>
  <input id=act placeholder="__ACTION_EXAMPLE__" autocomplete=off>
  <button id=go>▶</button>
</div>
<div id=overlay><p id=intro>__SCENE_INTRO__</p><p>▶ 点击进入场景</p></div>
<script>
const v=document.getElementById('v'), bar=document.getElementById('bar'),
      act=document.getElementById('act'), go=document.getElementById('go'),
      hint=document.getElementById('hint'), overlay=document.getElementById('overlay');

async function nextClip(){const r=await fetch('/api/next');return await r.json();}     // 阻塞直到该拍生成好
function playUrl(url){return new Promise(res=>{v.onloadeddata=()=>{v.play();res();};v.src=url;v.load();});}

async function turn(clip){        // 播这一拍;播完停在末帧、开放输入
  hint.textContent = clip.said || '';
  bar.classList.remove('on');
  await playUrl(clip.clip_url);
  v.onended=()=>{ bar.classList.add('on'); act.focus(); };
}
async function submit(){
  const text=act.value.trim(); if(!text)return;
  act.value=''; bar.classList.remove('on'); hint.textContent='世界回应中…';   // 生成等待(约十秒)
  await fetch('/api/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  turn(await nextClip());
}
go.onclick=submit;
act.onkeydown=e=>{ if(e.key==='Enter') submit(); };
overlay.onclick=async()=>{
  overlay.textContent='开场生成中…';
  const clip=await nextClip();    // 开场拍:feed 无输入自动产的第一拍
  overlay.style.display='none';
  turn(clip);
};
</script></body></html>"""


def main() -> None:
    cards = json.load(open(CARDS))
    card_id = os.environ.get("LUDENS_CARD", "denji")  # denji=英文 / duke=中文,启动时选故事
    card = next((c for c in cards if c["id"] == card_id), None)
    if card is None:
        raise SystemExit(f"未知故事卡 LUDENS_CARD={card_id!r};可选: {[c['id'] for c in cards]}")
    live_dir = os.environ.get("LUDENS_LIVE_DIR", os.path.join(LIVE_DIR, card_id))
    port = int(os.environ.get("LUDENS_PORT", "8790"))
    factory = JoyAIClipFactory(out_dir=live_dir)  # 真出片;需先跑 start_joyai_server.sh
    LudensPipeline(card, factory, live_dir).serve(port=port)


if __name__ == "__main__":
    main()
