"""aim 产"多 role 数据"(一条 messages,每轮一个消息 role state/assistant/…,role 自由扩展),
运镜层从这些 role 轮字段直取拼 R2V,零文本解析。最小闭环暂由 gemini 同套端点分饰三个决策面。

RosterExtractor —— 从卡抽跨镜常量 {name:{appearance,voice}}(锁身份的命根子,一次抽定,绝不每 shot 重产)。
ContentDirector —— 每 shot 产多 role 轮的动态部分:state 轮(场景+在场角色 status)+ assistant 轮(分角色 beats)。
CameraDirector  —— 吃一个 shot 的 state+assistant 两轮,产运镜/呈现。

外形/voice 由代码从 roster merge 进 state 轮,不让 LLM 每 shot 重产;把决策拼成 R2V 是 ShotRenderer 的事。
"""
from __future__ import annotations

from llm_client import LLMClient


def card_sheet(card: dict) -> str:
    # 角色设定段:[Character Card] 之后、user_profile 之前(挡掉 roleplay 规则与 Role Override Defense 噪声)
    body = card["system"].split("[Character Card]", 1)[-1]
    return body.split("user_profile:", 1)[0].strip()


ROSTER_SYS = (
    "You extract a visual roster from a roleplay character card, to lock cross-shot identity in a video model.\n"
    "For EVERY named character in the card, output their fixed physical appearance and an inferred speaking voice.\n"
    "Output ONLY one JSON object, no fences, no commentary:\n"
    '{"<name>": {"appearance": str, "voice": str}, ...}\n'
    "- name: exactly as written in the card.\n"
    "- appearance: one concise visual line (hair, eyes, build, signature outfit / distinctive features). "
    "Include non-humanoid characters, described visually.\n"
    "- voice: infer from personality since the card has no voice field, e.g. 'brash youthful tenor', "
    "'low measured baritone', 'soft airy soprano'.\n"
    "- Skip {{user}} and any purely silent off-screen observer."
)


class RosterExtractor:
    def __init__(self, llm: LLMClient, card: dict):
        self.llm = llm
        self.sheet = card_sheet(card)

    def extract(self) -> dict:
        roster = self.llm.call_json(ROSTER_SYS, f"[Character Card]\n{self.sheet}\n\nExtract the roster as JSON.")
        for name, v in roster.items():
            if not v.get("appearance") or not v.get("voice"):
                raise ValueError(f"roster entry missing appearance/voice: {name} -> {v}")
        return roster


CONTENT_SYS = (
    "You simulate an interactive roleplay scene, presented through short video shots. "
    "Resolve the player's attempted action against the current scene and character goals before presenting its result. "
    "Do not force a plot milestone or assume every attempted action succeeds.\n"
    "A shot is one continuous ~10-second clip. Write EXACTLY ONE spoken beat — a single short, natural line. "
    "Never cram several exchanges into one shot; let the story breathe slowly across shots.\n"
    "Output ONLY one JSON object, no fences, no commentary:\n"
    '{"state": {"location": str, "time": str, "mood": str, "environment": str, '
    '"characters": {"<name>": {"status": str}}, '
    '"objects": {"<object name>": {"location": str, "condition": str}}}, '
    '"assistant": {"beats": [{"who": str, "line": str, "action": str}]}}\n'
    "- state.characters: ONLY characters physically on screen this shot; status = what they are doing/feeling now. "
    "Use names EXACTLY as in [Cast].\n"
    "- state.objects: track the scene's interactive objects, including off-screen ones. Preserve their names, "
    "locations and conditions unless an actual action changes them; use {} if none are defined. "
    "Represent the resulting state of this turn. A proposed or refused action is not a completed change. "
    "Physical effects persist: wet objects do not spontaneously dry, moved objects do not reset, "
    "and containing a leak does not repair its source. Characters can initiate practical actions "
    "toward their own goals without inventing actions for the player.\n"
    "- environment: one concrete phrase of physical props / spatial elements / atmosphere events present at "
    "this location (objects, weather, activity). Do NOT describe overall color tone, light color, or grade — "
    "those are locked globally.\n"
    "- beats: a list holding EXACTLY ONE beat; who must be a name in state.characters; "
    "line = the exact short words spoken aloud (they will be voiced and lip-synced); "
    "action = the concurrent visible action or facial expression.\n"
    "- LINE LENGTH (critical): beat.line must be very short — one brief sentence, at most about 12 words "
    "(or ~20 Chinese characters). Each clip opens with a short silent pause before the character starts "
    "speaking, so a longer line will not finish before the ~10-second clip ends and gets cut off mid-word.\n"
    "- LANGUAGE: write state.location, time, mood, environment and every beat's action in ENGLISH. "
    "Write ONLY beat.line — the words actually spoken aloud — in the language named by [Dialogue language].\n"
    "- SCENE CONTINUITY: prefer to stay in the SAME scene as the previous shot — reuse its exact location string and "
    "keep time / mood / environment consistent — across several consecutive shots; move to a new location only when "
    "the story genuinely needs it.\n"
    "Do NOT write appearance or voice (locked elsewhere). Do NOT describe camera, shot size, or lighting "
    "framing (another module handles that).\n"
    "[User input] each shot is what the player {{user}} just did or said. Make THIS shot the world's and "
    "the other characters' direct, specific response to it — acknowledge it, never ignore it. {{user}} drives "
    "the story but stays OFF screen: never render {{user}} as a visible character and never give {{user}} a "
    "beat; the beats belong to the OTHER characters reacting to {{user}}.\n"
    "Stay in character and consistent with the card. Let consequences create the next situation; do not re-narrate the opening."
)


class ContentDirector:
    def __init__(self, llm: LLMClient, card: dict, roster: dict):
        self.llm = llm
        self.sheet = card_sheet(card)
        self.opening = card["welcome"].strip()
        self.roster = roster
        self.lang = card.get("lang", "en")  # 对话语言锁:引号内台词随卡语言,描述恒英文

    def next_shot(self, history: list[list[dict]], user_turn: str | None = None) -> list[dict]:
        raw = self.llm.call_json(CONTENT_SYS, self._user(history, user_turn))
        self._check(raw)
        return self._turns(raw, user_turn)

    def _turns(self, raw: dict, user_turn: str | None) -> list[dict]:
        state = raw["state"]
        for name, c in state["characters"].items():
            if name not in self.roster:
                raise ValueError(f"on-screen character {name!r} not in roster {list(self.roster)}")
            c["appearance"] = self.roster[name]["appearance"]  # 跨镜常量,从 roster 灌入
            c["voice"] = self.roster[name]["voice"]
        turns = [{"role": "state", "content": state},
                 {"role": "assistant", "content": raw["assistant"]}]
        if user_turn:
            turns.insert(0, {"role": "user", "content": user_turn})  # 玩家这拍输入,进 history 供 recap 追溯
        return turns

    def _user(self, history: list[list[dict]], user_turn: str | None) -> str:
        cast = ", ".join(self.roster)
        dlang = "Mandarin Chinese" if self.lang == "zh" else "English"
        act = user_turn.strip() if user_turn else (
            "(Story opening — no player input yet. Open the scene from the card's opening and wait for the player.)")
        return (f"[Character Card]\n{self.sheet}\n\n[Cast]\n{cast}\n\n"
                f"[Dialogue language]\n{dlang} — spoken lines (beat.line) only; keep all descriptions in English.\n\n"
                f"[User input]\n{act}\n\n"
                f"[Story so far]\n{self._recap(history)}\n\n"
                "Write the next shot as JSON — the world's response to [User input]. Only use characters from [Cast].")

    def _recap(self, history: list[list[dict]]) -> str:
        lines = [self.opening]
        for i, turns in enumerate(history, 1):
            u = next((t["content"] for t in turns if t["role"] == "user"), None)
            if u:
                lines.append(f"[you] {u}")
            state = _turn(turns, "state")
            beats = _turn(turns, "assistant")["beats"]
            said = " ".join(f'{b["who"]}: "{b["line"]}"' for b in beats)
            lines.append(f'[shot {i} @ {state["location"]}] {said}')
            lines.append("[Actions] " + " ".join(f'{b["who"]}: {b["action"]}' for b in beats))
            lines.append(f'[Objects after turn] {state.get("objects", {})}')
        if history:  # 显式点出当前场景,推动 director 沿用而非每片换景
            s = _turn(history[-1], "state")
            lines.append(f'[Current scene] {s["location"]} | {s["time"]} | {s["mood"]} | {s["environment"]} '
                         "— stay in this scene unless the story must move on.")
        return "\n".join(lines)

    def _check(self, raw: dict) -> None:
        for k in ("state", "assistant"):
            if k not in raw:
                raise ValueError(f"content missing {k!r}: {raw}")
        chars = raw["state"].get("characters")
        if not chars:
            raise ValueError(f"state has no on-screen characters: {raw['state']}")
        beats = raw["assistant"].get("beats")
        if not beats:
            raise ValueError(f"assistant has no beats: {raw['assistant']}")
        for b in beats:
            if not b.get("who") or not b.get("line"):
                raise ValueError(f"beat missing who/line: {b}")
            if b["who"] not in chars:
                raise ValueError(f"beat speaker {b['who']!r} not in state.characters {list(chars)}")


CAMERA_SYS = (
    "You are the cinematographer for a visual roleplay. Given a shot's scene state and its beats, "
    "decide how to frame and move the camera. You control ONLY framing and motion — never color, "
    "lighting, or mood (those are locked globally).\n"
    "Output ONLY one JSON object, no fences, no commentary:\n"
    '{"shot_size": str, "camera_move": str}\n'
    "- shot_size: ONLY one of — medium wide shot, medium shot, medium close-up, close-up. "
    "For object interactions, prefer a medium wide shot showing the character's hands, the relevant objects "
    "and their spatial relationship. Use facial close-ups only when the action does not need that context.\n"
    "- camera_move: ONLY one of — static, very slow push-in, slight handheld breath. "
    "Never pan, zoom, whip, or follow.\n"
    "- CONTINUITY: keep framing calm and steady; default to a stable frame that makes the action readable "
    "and avoid jarring jumps in shot size between consecutive shots.\n"
    "Show the action and its consequences; do not invent dialogue or new characters."
)


class CameraDirector:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def next_scene(self, turns: list[dict]) -> dict:
        state = _turn(turns, "state")
        beats = _turn(turns, "assistant")["beats"]
        present = ", ".join(state["characters"])
        said = " ".join(f'{b["who"]}: "{b["line"]}" ({b["action"]})' for b in beats)
        user = (f"[Scene]\n{state['location']} | {state['time']} | {state['mood']}\n{state['environment']}\n\n"
                f"[Shot]\nPresent: {present}\n{said}\n\nDecide the staging as JSON.")
        return self.llm.call_json(CAMERA_SYS, user)


def _turn(turns: list[dict], role: str) -> dict:
    return next(t["content"] for t in turns if t["role"] == role)
