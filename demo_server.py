"""下一代 Roleplay 视觉小说 demo（torch-free）：aim 单模型驱动剧情 + 世界状态，
状态经 HTTP 交给 render_server 渲成场景背景。prose 原样展示、渲染图做背景、caption=location·time。

    export AIM_KEY=...            # ⚠️ key 只从环境变量读，绝不写进任何文件
    python render_server.py &     # 先起渲染服务（torch，cuda:0）
    python demo_server.py         # http://<ip>:8765

aim serving 核心（块跳跃上下文 / 块边界写 state / clamp 兜底 / 跨轮去重）整套搬自
davr_mt/run_davr/demo/serve_demo.py 的单模型路径，判据未改；此处仅把散函数收进 Aim 类，
并在状态落定后调 render_server。会话落盘格式与 replay.py 一致（可离线重渲 LTX 动态）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
import uuid

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from scene_state import card_scene, ensure_location, first_json_object, normalize

HERE = os.path.dirname(os.path.abspath(__file__))
TURN_START, TURN_END = "<|turn>", "<turn|>"  # gemma4 轮分隔符
CHARS_PER_TOKEN = 3.2  # 英文 RP 文本实测字符→token 代理（训练侧切样同款）

# 自定义卡初始化：把用户输入的 personality/scenario 交给 init-LLM，产出可玩卡的三块可变内容。
# 端点主/兜底依次尝试（用户指定：gemini-3.8-flash 主、deepseek-v4 兜底）；配置对齐 data_pipeline/configs/llm.yaml。
INIT_ENDPOINTS = [
    {"name": "gemini-3.8-flash", "base_url": "https://kaon-router.kaonai.com/v1",
     "model": "google/gemini-3.8-flash", "key_env": "KAON_STATE_KEY",
     "params": {"temperature": 0.0, "max_tokens": 16384, "reasoning_effort": "low", "stream": False}},
    {"name": "deepseek-v4-pro", "base_url": "http://staging-kaon-router.flow.chat/v1",
     "model": "kaon/deepseek-v4-pro", "key_env": "KAON_KEY",
     "params": {"temperature": 0.7, "max_tokens": 16384, "enable_thinking": False, "stream": False}},
]
INIT_SYS = (
    "You turn a player's brief into a roleplay character card. Output ONLY one JSON object with keys "
    "title, character, welcome, scene — no markdown fences, no commentary.\n"
    "- title: a short display name for the character.\n"
    "- character: the character sheet body — personality, appearance, speech style, key relationships and "
    "backstory — as compact descriptive lines. Character/world content ONLY; never roleplay rules or meta.\n"
    "- welcome: the opening narration that starts the scene in second person, establishing where {{user}} is "
    "and what the character is doing right now. {{user}} is the human player; never speak or act for {{user}}.\n"
    "- scene: a SHORT English visual phrase for an image generator, form 'place — lighting/atmosphere/props'. "
    "Concrete and visual only, no narrative, no character names. English regardless of the brief's language.\n"
    "Write title/character/welcome in the SAME language as the brief (Chinese or English only). "
    "Stay grounded and consistent with the brief."
)
INIT_USER = "Personality:\n{personality}\n\nScenario:\n{scenario}"

app = FastAPI()
SESSIONS: dict[str, dict] = {}
CARDS: list[dict] = []
AIM = None
SCENE = None
MAKER = None
SESS_DIR = ""


def _dedup_key(t: str) -> str:
    # 实质重复的判据：归一化后前 24 字符（挡"同一句的微变体"，不只挡全等）
    return re.sub(r"[^\w]+", "", t.lower())[:24]


def _load_env(path: str) -> None:
    # 把已有 dotenv 的 KEY=VALUE 读进本进程环境（只补未设置的；key 绝不写进任何文件、不打印值）
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Aim:
    """单模型五轮型 serving：裸 /completions + role 轮头 prefill，止于轮分隔符。"""

    def __init__(self, base_url: str, model: str, key_env: str, block_turns: int = 10,
                 max_model_len: int = 8192, state_max_chars: int = 3000):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.key = os.environ.get(key_env, "")
        self.block_turns = block_turns
        self.max_model_len = max_model_len
        self.state_max_chars = state_max_chars

    def call(self, msgs: list[dict], role: str, n: int = 1, max_tokens: int = 768,
             temperature: float = 0.8, repetition_penalty: float = 1.0,
             top_p: float = 1.0, presence_penalty: float = 0.0) -> list[str]:
        prompt = "".join(f"{TURN_START}{m['role']}\n{m['content']}{TURN_END}\n" for m in msgs)
        prompt += f"{TURN_START}{role}\n"
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        body = {"model": self.model, "prompt": prompt, "n": n, "max_tokens": max_tokens,
                "temperature": temperature, "stop": [TURN_END, TURN_START]}
        if top_p != 1.0:
            body["top_p"] = top_p
        if repetition_penalty != 1.0:
            body["repetition_penalty"] = repetition_penalty  # vLLM 扩展字段，压长 JSON 循环
        if presence_penalty != 0.0:
            body["presence_penalty"] = presence_penalty  # 压制上下文已现 token（跨轮防复读）
        for attempt in range(3):
            try:
                r = requests.post(self.base_url + "/completions", json=body, headers=headers, timeout=180)
                r.raise_for_status()
                return [c["text"].strip() for c in r.json()["choices"]]
            except (requests.RequestException, KeyError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))

    def view(self, s: dict) -> list[dict]:
        # 块跳跃：[system] + [call_state + 锚 state] + 最近一块的轮次；真人 user 轮渲染为 autoreply。
        msgs = [{"role": "system", "content": s["card"]["system"]}]
        last = max((i for i, m in enumerate(s["history"]) if m["role"] == "state"), default=-1)
        if last >= 0:
            # 兜底必须在构造 prompt 时生效：否则 state 超窗后写新 state 的请求先 400，clamp 永执行不到而死锁
            raw = s["history"][last]["content"]
            if len(raw) > self.state_max_chars:
                try:
                    raw = json.dumps(self._clamp(json.loads(raw)), ensure_ascii=False)
                except (json.JSONDecodeError, ValueError):
                    raw = raw[:self.state_max_chars]
            msgs += [{"role": "call_state", "content": ""}, {"role": "state", "content": raw}]
        block = [{"role": "autoreply" if m["role"] == "user" else m["role"], "content": m["content"]}
                 for m in s["history"][last + 1:] if m["role"] in ("assistant", "autoreply", "user")]
        # 最后防线：块因任何原因没按时坍缩时丢最旧消息，保证 prompt 永远发得出去
        budget = int((self.max_model_len - 1024) * CHARS_PER_TOKEN) - sum(len(m["content"]) for m in msgs)
        while block and sum(len(m["content"]) for m in block) > budget:
            block.pop(0)
        return msgs + block

    def _prompt_tokens(self, s: dict) -> int:
        return int(sum(len(m["role"]) + len(m["content"]) + 4 for m in self.view(s)) / CHARS_PER_TOKEN)

    def block_full(self, s: dict, need_tokens: int = 0) -> bool:
        # token 预算说了算，轮数只是上限（serving 固定开销吃掉窗口，硬按轮数会撑爆 → 空回复）
        last = max((i for i, m in enumerate(s["history"]) if m["role"] == "state"), default=-1)
        n_turns = sum(1 for m in s["history"][last + 1:] if m["role"] == "assistant")
        if self._prompt_tokens(s) + need_tokens > self.max_model_len - 256:
            return True
        return n_turns >= self.block_turns

    @staticmethod
    def _shrink_value(v, budget: int):
        # 把一个 key 的值压进预算：list 砍尾、dict 砍尾、str 截断（都保留最早的条目）
        if isinstance(v, list):
            out = []
            for item in v:
                if len(json.dumps(out + [item], ensure_ascii=False)) > budget:
                    break
                out.append(item)
            return out or ([v[0]] if v else [])
        if isinstance(v, dict):
            out = {}
            for k, item in v.items():
                if len(json.dumps({**out, k: item}, ensure_ascii=False)) > budget:
                    break
                out[k] = item
            return out or dict(list(v.items())[:1])
        return str(v)[:max(budget - 2, 20)]

    def _clamp(self, state: dict) -> dict:
        # 工程兜底（非压缩策略）：超预算时按 key 占比收缩内容，绝不删 key（删 key = 替模型做灾难性遗忘）
        budget = self.state_max_chars
        if len(json.dumps(state, ensure_ascii=False)) <= budget:
            return state
        sizes = {k: len(json.dumps(v, ensure_ascii=False)) for k, v in state.items()}
        total = sum(sizes.values()) or 1
        out = {}
        for k, v in state.items():
            share = max(int(budget * sizes[k] / total), 60)
            out[k] = v if sizes[k] <= share else self._shrink_value(v, share)
        return out

    async def _write_state(self, s: dict, view: list[dict]) -> dict | None:
        # state 温度略低 + repetition_penalty 压长 JSON 的 token 循环；解析失败保留旧 state（自愈）
        raw = (await asyncio.to_thread(
            self.call, view + [{"role": "call_state", "content": ""}], "state", 1, 2048, 0.5, 1.08))[0]
        obj = first_json_object(raw)
        try:
            new = json.loads(obj) if obj else None
        except json.JSONDecodeError:
            new = None
        if not isinstance(new, dict) or not new:
            return None
        ns = normalize(new)
        if not ns.get("location") and not ns.get("characters"):
            return None  # 明显不是有效快照，保留旧 state
        new = self._clamp(new)
        s["state"] = new
        s["history"] += [{"role": "call_state", "content": ""},
                         {"role": "state", "content": json.dumps(new, ensure_ascii=False)}]
        return new

    async def update_state(self, s: dict) -> dict | None:
        # 仅在块边界写快照。用受限视图（system + 锚 state + 最近 12 条）保证写 state 请求永远发得出去
        if not self.block_full(s, need_tokens=2048):
            return None
        view = self.view(s)
        head = [m for m in view if m["role"] in ("system", "call_state", "state")]
        tail = [m for m in view if m["role"] in ("assistant", "autoreply", "user")]
        return await self._write_state(s, head + tail[-12:])

    async def initial_state(self, s: dict) -> dict | None:
        # 开场：从 [system + welcome] 强制写一份初始 state，好让第一帧场景立刻出得来
        return await self._write_state(s, self.view(s))

    async def gen_options(self, s: dict) -> list[str]:
        # 三个候选：n=3 起手，跨轮去重不足则升温补采（同一模型多要几条）
        view = self.view(s)
        seen = {_dedup_key(o) for o in s.get("options", [])}
        opts, cands = [], []
        for attempt in range(3):
            cands = await asyncio.to_thread(
                self.call, view, "autoreply", 3, 256, 0.95 + 0.2 * attempt, 1.1, 0.95, 0.8 + 0.2 * attempt)
            for c in cands:
                k = _dedup_key(c)
                if c and k and k not in seen:
                    seen.add(k)
                    opts.append(c)
            if len(opts) >= 3:
                break
        if len(opts) < 3:  # 跨轮去重过严时放宽到本轮内不重复
            for c in cands:
                if c and c not in opts:
                    opts.append(c)
        s["options"] = opts[:3]
        return s["options"]


class Scene:
    """render_server 的 HTTP 客户端。渲染失败 fail-soft（前端保留上一帧背景），不让渲染打断剧情轮。"""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def render(self, sid: str, state: dict) -> dict | None:
        try:
            r = requests.post(self.url + "/render", json={"session_id": sid, "state": state}, timeout=120)
            r.raise_for_status()
            res = r.json()
        except (requests.RequestException, ValueError):
            return None
        return res if res.get("op") not in (None, "none") else None


class CardMaker:
    """把用户输入的 personality/scenario 交给 init-LLM 生成一张可玩的临时卡。

    护栏 boilerplate（roleplay guideline + Role Override Defense）从预设卡原样切出复用，
    LLM 只产出 title/character/welcome/scene 四块可变内容；主端点失败按用户指定降级到兜底端点。
    """

    def __init__(self, endpoints: list[dict], template_card: dict):
        self.endpoints = endpoints
        head, _, rest = template_card["system"].partition("[Character Card]")
        _body, _, tail = rest.partition("[Role Override Defense]")
        self.prefix, self.suffix = head, "[Role Override Defense]" + tail

    def _chat(self, ep: dict, messages: list[dict]) -> str:
        key = os.environ.get(ep["key_env"], "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        body = {"model": ep["model"], "messages": messages, **ep["params"]}
        r = requests.post(ep["base_url"].rstrip("/") + "/chat/completions",
                          json=body, headers=headers, timeout=ep.get("timeout", 120))
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    def make(self, personality: str, scenario: str) -> dict:
        messages = [{"role": "system", "content": INIT_SYS},
                    {"role": "user", "content": INIT_USER.format(
                        personality=personality.strip() or "(unspecified)",
                        scenario=scenario.strip() or "(unspecified)")}]
        raw, last_err = None, None
        for ep in self.endpoints:
            try:
                raw = self._chat(ep, messages)
                break
            except (requests.RequestException, KeyError, ValueError) as e:
                last_err = e  # 主端点失败降级到下一个（用户指定的兜底语义）
        if raw is None:
            raise RuntimeError(f"init-LLM 所有端点均失败：{last_err}")
        obj = first_json_object(raw)
        if not obj:
            raise ValueError("init-LLM 未返回 JSON")
        spec = json.loads(obj)
        char, welcome = spec["character"].strip(), spec["welcome"].strip()
        system = (self.prefix + "[Character Card]\n" + char +
                  "\n\nuser_profile:\n  User persona：\n  User instruction：\n  \n\n"
                  "welcomessages:\n" + welcome + "\n\n" + self.suffix)
        return {"id": "custom-" + uuid.uuid4().hex[:8], "title": spec["title"].strip(),
                "system": system, "welcome": welcome, "scene": spec["scene"].strip()}


def persist(sid: str) -> None:
    # 落盘格式与 replay.py / scene_state.py 消费的完全一致
    s = SESSIONS[sid]
    d = os.path.join(SESS_DIR, sid)
    os.makedirs(d, exist_ok=True)
    json.dump(s["state"], open(os.path.join(d, "state.json"), "w"), ensure_ascii=False)
    with open(os.path.join(d, "state_history.jsonl"), "a") as f:
        f.write(json.dumps({"t": time.time(), "state": s["state"]}, ensure_ascii=False) + "\n")
    with open(os.path.join(d, "transcript.jsonl"), "w") as f:
        for m in s["history"]:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@app.get("/")
async def index():
    return HTMLResponse(HTML)


@app.get("/api/cards")
async def cards():
    return [{"id": c["id"], "title": c["title"]} for c in CARDS]


@app.post("/api/session")
async def new_session(body: dict):
    if body.get("personality") or body.get("scenario"):
        try:
            card = await asyncio.to_thread(MAKER.make, body.get("personality", ""), body.get("scenario", ""))
        except (RuntimeError, ValueError, KeyError) as e:
            raise HTTPException(502, f"自定义卡初始化失败：{e}")
    else:
        card = next((c for c in CARDS if c["id"] == body.get("card_id")), CARDS[0])
    sid = uuid.uuid4().hex[:12]
    s = {"card": card, "history": [{"role": "assistant", "content": card["welcome"]}],
         "state": {}, "options": [], "seed_loc": card_scene(card)}
    SESSIONS[sid] = s
    await AIM.initial_state(s)
    s["state"] = ensure_location(s["state"], s["seed_loc"])  # 开场兜底：模型这时通常还没 location
    scene = await asyncio.to_thread(SCENE.render, sid, s["state"])
    opts = await AIM.gen_options(s)
    persist(sid)
    return {"session_id": sid, "title": card["title"], "welcome": card["welcome"],
            "options": opts, "scene": scene}


@app.get("/api/session/{sid}/state")
async def get_state(sid: str):
    if sid not in SESSIONS:
        raise HTTPException(404)
    return SESSIONS[sid]["state"]


@app.post("/api/session/{sid}/step")
async def step(sid: str, body: dict):
    if sid not in SESSIONS:
        raise HTTPException(404)
    s, mode = SESSIONS[sid], body.get("mode", "auto")
    if mode == "user" and body.get("text", "").strip():
        s["history"].append({"role": "user", "content": body["text"].strip()})
        shown = None
    else:
        opts = s.get("options") or await AIM.gen_options(s)
        text = opts[min(int(body.get("pick", 0)), len(opts) - 1)] if opts else "..."
        s["history"].append({"role": "autoreply", "content": text})
        shown = text

    async def gen():
        if shown is not None:
            yield sse({"type": "user_turn", "text": shown})
        # 生成前先兜窗口：装不下就地坍缩（判据用写 state 的预算，否则 assistant 觉得能写、state 觉得写不下 → 死锁）
        if AIM.block_full(s, need_tokens=2048):
            await AIM.update_state(s)
        reply = (await asyncio.to_thread(AIM.call, AIM.view(s), "assistant", 1, 768))[0]
        s["history"].append({"role": "assistant", "content": reply})
        for i in range(0, len(reply), 24):  # 伪流式 typewriter
            yield sse({"type": "token", "text": reply[i:i + 24]})
            await asyncio.sleep(0.03)
        # 阅读时间窗：state 更新与候选预取并行；state 落定后再渲染场景
        t = asyncio.create_task(AIM.update_state(s))
        opts = await AIM.gen_options(s)
        await t
        s["state"] = ensure_location(s["state"], s["seed_loc"])  # location 长出来前一直用卡片场景兜底
        scene = await asyncio.to_thread(SCENE.render, sid, s["state"])
        persist(sid)
        yield sse({"type": "meta", "options": opts, "state": s["state"], "scene": scene,
                   "turns": sum(1 for m in s["history"] if m["role"] == "assistant")})

    return StreamingResponse(gen(), media_type="text/event-stream")


HTML = r'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>下一代 Roleplay · 场景跟着剧情变</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}html,body{height:100%}
body{background:#05050a;color:#f0f0f5;font-family:-apple-system,"Segoe UI","PingFang SC",sans-serif;overflow:hidden}
#stage{position:fixed;inset:0}
.bg{position:absolute;inset:0;background-size:cover;background-position:center;opacity:0;transition:opacity 1.2s ease}
.bg.on{opacity:1}
#scrim{position:absolute;inset:0;background:linear-gradient(0deg,rgba(5,5,10,.94) 0%,rgba(5,5,10,.35) 42%,rgba(5,5,10,.12) 100%);pointer-events:none}
#caption{position:absolute;top:16px;left:18px;font-size:12px;letter-spacing:.5px;color:#cfe;background:rgba(0,0,0,.4);backdrop-filter:blur(6px);border:1px solid rgba(120,180,160,.28);border-radius:14px;padding:6px 12px;display:none}
#worldbtn{position:absolute;top:14px;right:16px;font-size:11px;color:#9de0c4;background:rgba(15,26,22,.6);backdrop-filter:blur(6px);border:1px solid rgba(40,90,70,.6);border-radius:14px;padding:6px 12px;cursor:pointer;z-index:12}
#vnwrap{position:absolute;left:0;right:0;bottom:0;padding:0 18px 18px;max-width:660px;margin:0 auto}
#userline{font-size:12.5px;color:#b7e0c8;margin:0 8px 8px 0;text-align:right;min-height:1.2em}
#vn{background:rgba(10,12,20,.74);backdrop-filter:blur(10px);border:1px solid rgba(120,120,160,.25);border-radius:16px;padding:15px 18px;max-height:40vh;overflow-y:auto}
#who{font-size:12px;color:#b0a0f0;font-weight:600;margin-bottom:6px}
#prose{font-size:15px;line-height:1.75;white-space:pre-wrap}
.dock{max-width:660px;margin:12px auto 0}
.bar{display:flex;flex-direction:column;gap:7px;margin-bottom:9px}
.opt{background:rgba(22,22,34,.72);backdrop-filter:blur(6px);border:1px solid rgba(90,90,130,.5);border-radius:13px;padding:10px 14px;font-size:12.5px;color:#d0d0e0;cursor:pointer;text-align:left;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.opt:hover{background:rgba(42,42,64,.9);color:#fff}
.opt.go{background:#4a2a7a;border-color:#8a6ae0;color:#fff;text-align:center;-webkit-line-clamp:1}
.inrow{display:flex;gap:8px}
#inp{flex:1;background:rgba(14,14,22,.82);border:1px solid rgba(80,80,120,.6);border-radius:16px;padding:9px 14px;font-size:13px;color:#eee;outline:none}
#send{background:#2a6a48;border:none;border-radius:16px;padding:9px 16px;font-size:12px;color:#fff;cursor:pointer}
.think{color:#889;font-size:11px;text-align:center;padding:6px}
#panel{position:fixed;top:0;right:-360px;width:340px;height:100%;background:rgba(8,14,12,.97);backdrop-filter:blur(12px);border-left:1px solid #16281f;padding:56px 18px 18px;transition:right .3s;z-index:30;overflow-y:auto}
#panel.open{right:0}#panel h3{font-size:13px;color:#6a9a8a;margin-bottom:12px}
#panel .row{margin:7px 0;font-size:12px;color:#a8c8b8;word-break:break-word}#panel .k{color:#5cbf94;font-weight:600}
#start{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:26px;background:radial-gradient(120% 90% at 50% 0%,#131326 0%,#05050a 70%);z-index:15}
#start h1{font-size:20px;font-weight:600}#start p{font-size:12.5px;color:#8a8a9a;margin-bottom:6px}
.pick{width:min(88%,420px);padding:13px 16px;border-radius:14px;background:rgba(22,22,34,.8);border:1px solid rgba(100,90,160,.5);font-size:14px;color:#e6e6f2;cursor:pointer}
.pick:hover{background:#3a2a5a;border-color:#8a6ae0;color:#fff}
#start{overflow-y:auto}
.divider{width:min(88%,420px);text-align:center;color:#6a6a7a;font-size:11px;margin:12px 0 2px;border-top:1px solid rgba(90,90,130,.25);padding-top:12px}
#custom{width:min(88%,420px);display:flex;flex-direction:column;gap:7px}
#custom textarea{background:rgba(14,14,22,.82);border:1px solid rgba(80,80,120,.6);border-radius:12px;padding:9px 12px;font-size:12.5px;color:#eee;outline:none;resize:vertical;min-height:46px;font-family:inherit;line-height:1.5}
#custom .go2{padding:11px;border-radius:13px;background:#2a6a48;border:none;color:#fff;font-size:13px;cursor:pointer}
#custom .go2:disabled{opacity:.6;cursor:default}
</style></head><body>
<div id="stage">
  <div class="bg" id="bgA"></div><div class="bg" id="bgB"></div>
  <div id="scrim"></div>
  <div id="caption"></div>
  <div id="worldbtn" onclick="document.getElementById('panel').classList.toggle('open')">🌐 世界状态</div>
  <div id="vnwrap" style="display:none">
    <div id="userline"></div>
    <div id="vn"><div id="who"></div><div id="prose"></div></div>
    <div class="dock"><div class="bar" id="opts"></div>
      <div class="inrow"><input id="inp" placeholder="打一句话，附身进故事…（可选）"><button id="send" onclick="sendUser()">附身</button></div>
    </div>
  </div>
  <div id="start"><h1>下一代 Roleplay · 场景跟着剧情变</h1><p>选一个角色开始（状态驱动的一致场景 + 无限流）</p></div>
</div>
<div id="panel"><h3>🌐 世界状态（模型的记忆 · 落盘持久化）</h3><div id="pbody"><div class="row">开始对话后出现</div></div></div>
<script>
let SID=null,TITLE='',busy=false,curBg='B';
const bgA=document.getElementById('bgA'),bgB=document.getElementById('bgB');
const prose=document.getElementById('prose'),who=document.getElementById('who'),opts=document.getElementById('opts');
const cap=document.getElementById('caption'),userline=document.getElementById('userline');
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function setBg(url){if(!url)return;const cur=curBg==='A'?bgA:bgB,nxt=curBg==='A'?bgB:bgA;
  nxt.style.backgroundImage='url('+url+')';nxt.classList.add('on');cur.classList.remove('on');curBg=curBg==='A'?'B':'A'}
function setScene(sc){if(sc&&sc.url){setBg(sc.url);if(sc.caption){cap.textContent=sc.caption;cap.style.display='block'}}}
function renderOpts(list){opts.innerHTML='';(list||[]).forEach((o,i)=>{const b=document.createElement('div');b.className='opt';b.textContent=o;b.title=o;b.onclick=()=>step('pick',null,i);opts.appendChild(b)});
  const g=document.createElement('div');g.className='opt go';g.textContent='↑ 继续';g.onclick=()=>step('auto');opts.appendChild(g)}
function renderState(o){const p=document.getElementById('pbody');p.innerHTML='';for(const k in o){let v=o[k];if(v&&typeof v==='object')v=JSON.stringify(v);
  const r=document.createElement('div');r.className='row';r.innerHTML='<span class="k">'+esc(k)+'</span> · '+esc(String(v).slice(0,240));p.appendChild(r)}}
async function step(mode,text,pick){if(busy||!SID)return;busy=true;opts.innerHTML='<div class="think">生成中…</div>';
  if(mode==='user'){userline.textContent='你：'+text}
  const res=await fetch('/api/session/'+SID+'/step',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,text,pick})});
  const rd=res.body.getReader(),dec=new TextDecoder();let buf='',fresh=true;
  while(true){const{done,value}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
    while((i=buf.indexOf('\n\n'))>=0){const line=buf.slice(0,i);buf=buf.slice(i+2);if(!line.startsWith('data: '))continue;
      const ev=JSON.parse(line.slice(6));
      if(ev.type==='user_turn'){userline.textContent='你：'+ev.text}
      else if(ev.type==='token'){if(fresh){prose.textContent='';who.textContent=TITLE.split(' · ')[0];fresh=false}prose.textContent+=ev.text;prose.scrollTop=prose.scrollHeight}
      else if(ev.type==='meta'){renderOpts(ev.options);renderState(ev.state);setScene(ev.scene);
        cap.dataset.turn=ev.turns}}}
  busy=false}
function sendUser(){const v=document.getElementById('inp').value.trim();if(!v)return;document.getElementById('inp').value='';step('user',v)}
document.getElementById('inp').addEventListener('keydown',e=>{if(e.key==='Enter')sendUser()});
async function pickCard(id){if(busy)return;busy=true;
  document.getElementById('start').innerHTML='<div class="think">开场中…</div>';
  const r=await(await fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({card_id:id})})).json();
  SID=r.session_id;TITLE=r.title;
  document.getElementById('start').style.display='none';document.getElementById('vnwrap').style.display='block';
  who.textContent=TITLE.split(' · ')[0];prose.textContent=r.welcome;setScene(r.scene);renderOpts(r.options);busy=false}
async function startCustom(){if(busy)return;
  const p=document.getElementById('cp').value.trim(),s=document.getElementById('cs').value.trim();
  if(!p&&!s){alert('至少填一点 Personality 或 Scenario');return}
  busy=true;const btn=document.getElementById('cgo'),t0=btn.textContent;btn.textContent='初始化中…（约十几秒）';btn.disabled=true;
  try{const res=await fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({personality:p,scenario:s})});
    if(!res.ok)throw new Error(((await res.json().catch(()=>({}))).detail)||('HTTP '+res.status));
    const r=await res.json();SID=r.session_id;TITLE=r.title;
    document.getElementById('start').style.display='none';document.getElementById('vnwrap').style.display='block';
    who.textContent=TITLE.split(' · ')[0];prose.textContent=r.welcome;setScene(r.scene);renderOpts(r.options);
  }catch(e){alert('初始化失败：'+e.message)}
  btn.textContent=t0;btn.disabled=false;busy=false}
(async()=>{const cs=await(await fetch('/api/cards')).json();const st=document.getElementById('start');
  cs.forEach(c=>{const b=document.createElement('div');b.className='pick';b.textContent=c.title;b.onclick=()=>pickCard(c.id);st.appendChild(b)});
  const dv=document.createElement('div');dv.className='divider';dv.textContent='—— 或自定义一个角色 ——';st.appendChild(dv);
  const box=document.createElement('div');box.id='custom';
  box.innerHTML='<textarea id="cp" placeholder="Personality：性格 / 外形 / 说话风格…"></textarea>'
    +'<textarea id="cs" placeholder="Scenario：开场设定——{{user}} 此刻在哪、正发生什么…"></textarea>'
    +'<button class="go2" id="cgo" onclick="startCustom()">✏️ 生成并开始</button>';
  st.appendChild(box)})();
</script></body></html>'''


def main():
    global AIM, SCENE, MAKER, CARDS, SESS_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--aim_url", default="http://model-test-kaon-mia-v0-yotta2.flow.chat/v1")
    ap.add_argument("--aim_model", default="kaonai/kaon-mia-v0")
    ap.add_argument("--aim_key_env", default="AIM_KEY", help="⚠️ key 只从环境变量读，绝不写进文件")
    ap.add_argument("--env_file", default="/mnt/local/sean/data_pipeline/.env",
                    help="从已有 dotenv 读 key 进环境（默认 data_pipeline/.env，含 KAON_STATE_KEY/KAON_KEY）；传 '' 关闭")
    ap.add_argument("--render_url", default="http://127.0.0.1:8781")
    ap.add_argument("--cards", default=os.path.join(HERE, "seed_cards.json"))
    ap.add_argument("--sessions", default=os.path.join(HERE, "sessions"))
    ap.add_argument("--scenes", default=os.path.join(HERE, "out/live"))
    ap.add_argument("--block_turns", type=int, default=10)
    ap.add_argument("--max_model_len", type=int, default=8192)
    ap.add_argument("--state_max_chars", type=int, default=3000)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    _load_env(args.env_file)

    AIM = Aim(args.aim_url, args.aim_model, args.aim_key_env, args.block_turns,
              args.max_model_len, args.state_max_chars)
    if not AIM.key:
        raise SystemExit(f"缺 API key：请先  export {args.aim_key_env}=...  （key 绝不写进文件）")
    SCENE = Scene(args.render_url)
    CARDS = json.load(open(args.cards))
    MAKER = CardMaker(INIT_ENDPOINTS, CARDS[0])
    for ep in INIT_ENDPOINTS:
        if not os.environ.get(ep["key_env"]):
            print(f"[demo] ⚠️ 自定义卡初始化端点 {ep['name']} 缺 key（env {ep['key_env']}），将自动降级")
    SESS_DIR = args.sessions
    os.makedirs(args.scenes, exist_ok=True)
    app.mount("/scenes", StaticFiles(directory=args.scenes), name="scenes")
    print(f"[demo] aim={args.aim_url} render={args.render_url} cards={len(CARDS)} → :{args.port}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
