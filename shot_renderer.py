"""ShotRenderer:确定性胶水(非模型),把 aim 的多 role 数据 + 运镜决策拼成 JoyAI Echo 1.5 的 R2V payload。

一个 shot 的 (state 轮 + assistant 轮) + camera → 一条 R2VRequest payload(prompt + memory_slots + 尺寸)。
prompt 是自然语言(JoyAI 只吃 NL,≤1500 chars):场景 + 每角色 ID_x 外形/嗓音 + beats 台词/动作 + 镜头 + 反字幕。
跨 shot 的 name→ID_x 分配稳定累积;跨镜身份锁由 assets 表驱动:空 → memory_slots=[](纯 prompt 弱锁),
填了每角色 canonical 图/音 → 自动升级成 the_last_visa 那种 image_url+audio_url 强锚。契约见 wm_repos 的 r2v_schema.py。
"""
from __future__ import annotations

MAX_MEMORY_SLOTS = 7  # 对齐 r2v_schema.MAX_MEMORY_SLOTS
MAX_PROMPT = 1500     # JoyAI 硬上限;超了它砍尾巴=正好砍掉末尾 NEGATIVES(反字幕/锁脸),故我方主动裁,绝不交给它砍

NEGATIVES = (
    "Everyone keeps the same face, hair, and clothes throughout; "
    "lips synced to speech. No subtitles, captions, on-screen text, or writing."
)


class ShotRenderer:
    def __init__(self, work_id: str, assets: dict | None = None, num_frames: int = 241,
                 width: int = 1280, height: int = 736, seed: int = 42, duration_sec: float = 9.64,
                 style: str = "anime", grade: str = ""):
        self.work_id = work_id
        self.assets = assets or {}  # name -> {"image_url": str, "audio_url": str|None};空则纯 prompt 弱锁
        self.num_frames, self.width, self.height = num_frames, width, height
        self.seed, self.duration_sec = seed, duration_sec
        self.style = style  # 跨镜画风锁:每 shot 恒定注入,别让模型在写实/动漫间摇摆(真人卡通乱跳的根因)
        self.grade = grade  # 跨镜色调锁:全片统一 color grade 恒定注入,色调话语权从 director 收归到此
        self.ids: dict[str, str] = {}  # name -> ID_x,跨 shot 稳定

    def render(self, index: int, turns: list[dict], camera: dict) -> dict:
        by_role = {t["role"]: t["content"] for t in turns}
        state, assistant = by_role["state"], by_role["assistant"]
        chars = state["characters"]
        for name in chars:  # 按在场顺序稳定分配 ID
            self._id(name)

        establishing = (f"In the {state['location']} ({state['time']}); "
                        f"{state['environment']}. Mood: {state['mood']}.")
        cast = " ".join(f"{self.ids[n]} is {n}: {c['appearance']} Voice: {c['voice']}."
                        for n, c in chars.items())
        cam = f"Camera: {camera['shot_size']}, {camera['camera_move']}."

        prompt, beats = self._fit(establishing, cast, assistant["beats"], cam)
        assistant["beats"] = beats  # 极端超长丢了末尾整 beat 时同步给字幕/配音侧(ShotUnit.beats 在 render 后从 turns 取)

        return {
            "work_id": self.work_id,
            "shot_id": f"shot_{index:03d}",
            "prompt": prompt,
            "condition_img": None,
            "memory_slots": self._slots(chars),
            "num_frames": self.num_frames,
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "duration_sec": self.duration_sec,
        }

    def _action(self, beats: list[dict]) -> str:
        return " ".join(f'{self.ids[b["who"]]} {b["action"]} — "{b["line"]}"' for b in beats)

    def _fit(self, establishing: str, cast: str, beats: list[dict], cam: str) -> tuple[str, list[dict]]:
        """预算保护式组装:台词优先全留;超 1500 先压外形描述(cast),压光还超(台词真·特别长)才按 beat 整句丢末尾。"""
        style = f"Consistent {self.style} art style in every shot; coherent, on-model character designs."

        def build(cast_text: str, bs: list[dict]) -> str:
            return " ".join(s for s in (style, self.grade, establishing, cast_text, self._action(bs), cam, NEGATIVES) if s)

        prompt = build(cast, beats)
        if len(prompt) <= MAX_PROMPT:
            return prompt, beats
        cast = self._trim(cast, len(cast) - (len(prompt) - MAX_PROMPT))  # 按超出量把外形截到词边界
        beats = list(beats)
        while len(beats) > 1 and len(build(cast, beats)) > MAX_PROMPT:
            beats.pop()  # 整句丢末尾 beat,永不砍半句台词
        return build(cast, beats), beats

    @staticmethod
    def _trim(text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        return text[:budget].rsplit(" ", 1)[0] if budget > 0 else ""

    def _id(self, name: str) -> str:
        if name not in self.ids:
            self.ids[name] = f"ID_{chr(ord('A') + len(self.ids))}"
        return self.ids[name]

    def _slots(self, chars: dict) -> list[dict]:
        slots = []
        for name in chars:
            asset = self.assets.get(name)
            if not asset:
                continue  # 无 canonical 资产的角色只能靠 prompt 文字锁
            slots.append({"image_url": asset["image_url"], "audio_url": asset.get("audio_url"),
                          "metadata": {"id": self.ids[name], "source": "roster_canonical"}})
        return slots[:MAX_MEMORY_SLOTS]
