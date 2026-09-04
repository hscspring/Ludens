"""state 轮 → 视觉语言：把 aim 的 state 快照翻成场景 prompt / 编辑指令 / 运动段落。

纯逻辑（含状态机 SceneState），无模型依赖，可单独 CPU 跑（见 __main__）。视觉相关字段只有
location / time / characters(appearance,current_action) / possessions；
relationship / open_threads / arc_summary 是叙事维度，不进画面。
live(demo) 与离线(replay) 共用 SceneState 与这里的解析/归一。
"""

from __future__ import annotations

import json
import re
import sys

# characters 里混进的非角色噪声键（state 抽取产物）
JUNK_CHARACTERS = {"Location", "Setting", "Environment"}
# 无信息量的字段值，归一成"缺失"，不进 prompt、不触发编辑
UNINFORMATIVE = {"unknown", "n/a", "na", "none", "null", "tbd", ""}


def first_json_object(text: str) -> str | None:
    # aim 的 state 轮偶发多闭/少闭一个括号（fat characters dict），贪婪 {.*} 会过度匹配整段；
    # 按括号深度扫到第一个平衡点截取。实测 4/5 通过 vs 贪婪 1/5。
    i = text.find("{")
    if i < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None


def _clean(value: object) -> str | None:
    if isinstance(value, str) and value.strip() and value.strip().lower() not in UNINFORMATIVE:
        return value.strip()
    return None


def normalize(state: dict) -> dict:
    # 形状保险层（非必需——shape 跨轮稳定）：characters/character 的 list-of-names → dict{name:{}}；
    # location 的 {current:...} → str。只归形状不改语义，存进 history 的仍是模型原生 state。
    out = dict(state)
    chars = state.get("characters", state.get("character"))
    if isinstance(chars, list):
        out["characters"] = {str(n): {} for n in chars if n}
    elif isinstance(chars, dict):
        out["characters"] = chars
    else:
        out["characters"] = {}
    out.pop("character", None)
    loc = state.get("location")
    if isinstance(loc, dict):
        out["location"] = loc.get("current") or loc.get("name")
    return out


def present_characters(state: dict) -> dict[str, dict]:
    out = {}
    for name, value in (state.get("characters") or {}).items():
        if name in JUNK_CHARACTERS or not isinstance(value, dict):
            continue
        desc = {}
        for k in ("appearance", "current_action"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                desc[k] = v.strip()
        out[name] = desc
    return out


def _char_phrase(name: str, desc: dict) -> str:
    bits = [desc[k] for k in ("appearance", "current_action") if desc.get(k)]
    return f"{name} — {'; '.join(bits)}" if bits else name


def _notable_items(state: dict) -> list[str]:
    items = []
    for container, content in (state.get("possessions") or {}).items():
        if isinstance(content, list):
            items += [str(x) for x in content if x]
        elif isinstance(content, dict):
            items += [k for k in content if k]
    return items


def scene_prompt(state: dict) -> str:
    parts = ["A cinematic film still, photoreal, shallow depth of field."]
    if loc := _clean(state.get("location")):
        parts.append(f"Setting: {loc}.")
    if t := _clean(state.get("time")):
        parts.append(f"Time: {t}.")
    for name, desc in present_characters(state).items():
        if desc:
            parts.append(f"{_char_phrase(name, desc)}.")
    if items := _notable_items(state):
        parts.append("Visible: " + ", ".join(items[:6]) + ".")
    return " ".join(parts)[:700]


def caption(state: dict) -> str:
    # 左上角小胶囊：location · time。location 取破折号/句号前那截当短地名，超长再按词界截断。
    state = normalize(state)
    loc = _clean(state.get("location"))
    if loc:
        loc = re.split(r"[—;\n]", loc)[0].strip()  # 只切破折号/分号/换行；不切 "." 免误伤 U.A. 等缩写
        if len(loc) > 48:
            loc = loc[:48].rsplit(" ", 1)[0] + "…"
    t = _clean(state.get("time"))
    return " · ".join(b for b in (loc, t) if b)


def card_scene(card: dict) -> str:
    # 开场场景兜底。这个模型的 location 要攒十几轮才长出来（实测第 ~16 轮），开场先用卡片给的。
    # 优先卡片预设的 scene（一句视觉短语，地名在前、破折号后接氛围）；没有才退回 welcome 首段旁白。
    if scene := _clean(card.get("scene")):
        return scene
    text = re.sub(r"\*", "", (card.get("welcome") or "").split("\n", 1)[0])
    text = text.replace("{{user}}", "the observer").strip()
    out, total = [], 0
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if out and total + len(sent) > 180:
            break
        out.append(sent)
        total += len(sent) + 1
    return " ".join(out).strip()


def ensure_location(state: dict, fallback: str) -> dict:
    # 只补缺：模型没给可用 location（含 "Unknown" 这类无信息值）时，填卡片预设场景；给了就原样返回。
    # 返回浅拷贝、只加 location 一个键，原生 characters 一字不动 → 落盘/离线 replay 一致。
    if not fallback or _clean(normalize(state).get("location")):
        return state
    return {**state, "location": fallback}


def scene_instruction(prev: dict, new: dict) -> str | None:
    # 只有 location/time/角色在场/appearance 变化算"场景变了"；current_action 每轮都变，不触发
    edits = []
    for field, template in (
        ("location", "Change the setting to: {}."),
        ("time", "The time is now {}; adjust lighting and atmosphere."),
    ):
        new_v = _clean(new.get(field))
        if new_v and new_v != _clean(prev.get(field)):
            edits.append(template.format(new_v))

    prev_ch, new_ch = present_characters(prev), present_characters(new)
    for name in new_ch.keys() - prev_ch.keys():
        edits.append(f"{_char_phrase(name, new_ch[name])} enters the scene.")
    for name in prev_ch.keys() - new_ch.keys():
        edits.append(f"{name} is no longer in the scene.")
    for name in new_ch.keys() & prev_ch.keys():
        if (new_app := new_ch[name].get("appearance")) and new_app != prev_ch[name].get("appearance"):
            edits.append(f"{name} now appears: {new_app}.")

    return " ".join(edits) if edits else None


def motion_hint(state: dict) -> str:
    # LTX-2.5 短 prompt 会退化，需要一整段描述性文字
    loc = _clean(state.get("location")) or "the scene"
    t = _clean(state.get("time")) or "the present moment"
    actions = [
        f"{name} {desc['current_action']}"
        for name, desc in present_characters(state).items()
        if desc.get("current_action")
    ]
    para = f"A cinematic shot of {loc} at {t}. "
    if actions:
        para += " ".join(a.rstrip(".") + "." for a in actions) + " "
    para += (
        "Gentle ambient motion: subtle camera drift, soft shifting light, "
        "drifting atmospheric particles, quiet natural movement. "
        "Filmic, photoreal, shallow depth of field, soft volumetric lighting."
    )
    return para


class SceneState:
    """逐轮增量决策的状态机：location 变 / 链过长 → create 干净锚点；同 location 内可见变化 → 浅 edit。

    持有跨轮生命周期状态（上一帧 state、当前 location、edit 链长），故为类而非散函数。
    max_chain：同一 location 连续 edit 超过它就强制 re-create，避免链式重编码劣化累积。
    """

    def __init__(self, max_chain: int = 4):
        self.max_chain = max_chain
        self.prev: dict | None = None
        self.cur_loc: str | None = None
        self.chain = 0

    def step(self, state: dict) -> tuple[str, str] | None:
        # 返回 (op, reason) 或 None（本轮无可见变化，不出帧、不推进 prev）
        state = normalize(state)
        loc = _clean(state.get("location"))
        if self.prev is None:
            if not loc:
                return None
            self.prev, self.cur_loc, self.chain = state, loc, 0
            return "create", scene_prompt(state)
        instr = scene_instruction(self.prev, state)
        if instr is None:
            return None
        if (loc and loc != self.cur_loc) or self.chain >= self.max_chain:
            op, reason = "create", scene_prompt(state)
            self.cur_loc, self.chain = loc or self.cur_loc, 0
        else:
            op, reason = "edit", instr
            self.chain += 1
        self.prev = state
        return op, reason


def replay_plan(states: list[dict], max_chain: int = 4) -> list[dict]:
    scene = SceneState(max_chain=max_chain)
    frames = []
    for idx, state in enumerate(states):
        if plan := scene.step(state):
            op, reason = plan
            frames.append({"idx": idx, "op": op, "reason": reason, "state": state})
    return frames


if __name__ == "__main__":
    path = sys.argv[1]
    states = [json.loads(ln)["state"] for ln in open(path) if ln.strip()]
    plan = replay_plan(states)
    print(f"{len(states)} snapshots -> {len(plan)} rendered frames\n")
    for f in plan:
        loc = f["state"].get("location")
        print(f"[{f['idx']:>4}] {f['op']:<6} loc={loc!r}")
        print(f"        {f['reason'][:160]}")
