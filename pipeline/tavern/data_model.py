from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class SceneCreate(BaseModel):
    personality: str = Field(min_length=1, max_length=24000)
    scenario: str = Field(default="", max_length=24000)
    welcomeMessage: str = Field(min_length=1, max_length=24000)


class SceneProp(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    name: str
    description: str
    contents: str = ""


class ScenePlan(BaseModel):
    supported: bool
    reason: str = ""
    title: str
    character: str
    player_role: str
    entry: str
    prologue: str
    opening_line: str
    image_prompt: str
    objects: list[SceneProp] = Field(min_length=1, max_length=4)


class Action(BaseModel):
    kind: Literal["bucket_catch", "bucket_floor", "crate_safe", "crate_wet", "ledger_safe", "ledger_crate", "wipe", "wring", "talk", "wait", "crate_left", "crate_right", "crate_return", "inspect", "move"]
    target: str = Field(default="", max_length=80)
    text: str = Field(default="", max_length=1000)
    delta: Literal[-16, 0, 16] = 0
    animate: bool = True


class ReplyOption(BaseModel):
    intent: Literal["ask", "comfort", "challenge", "decline", "agree", "chat"] = "chat"
    label: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=160)


class ObjectLead(BaseModel):
    hint: str = Field(default="", max_length=120)
    options: list[ReplyOption] = Field(default_factory=list, max_length=2)


class ObjectStory(BaseModel):
    id: str
    name: str
    description: str
    background: str
    contents: str = ""
    lead: ObjectLead = Field(default_factory=ObjectLead)
    notice: bool = False
    visual: str = ""


class StoryMoment(BaseModel):
    target: str
    title: str = Field(min_length=1, max_length=32)
    image: str = Field(min_length=1, max_length=500)


class SceneSetting(BaseModel):
    music: Literal["tense", "calm", "warm", "quiet"] = "quiet"
    title: str
    character: str
    motive: str
    background: str
    boundary: str
    objects: list[ObjectStory]
    opportunities: list[str] = Field(min_length=1, max_length=3)
    suggestions: list[ReplyOption] = Field(default_factory=list, max_length=3)


class ObjectQuote(BaseModel):
    target: str
    quote: str = Field(min_length=1, max_length=300)


class ObjectState(BaseModel):
    id: str
    description: str = Field(min_length=1, max_length=300)
    location: str = Field(min_length=1, max_length=200)
    visible: bool
    visual: str = Field(max_length=350)


class SceneReply(BaseModel):
    object_updates: list[ObjectState] = Field(default_factory=list)
    appearance: str | None = Field(default=None, max_length=700)
    reactions: list[str] = Field(default_factory=list, max_length=1)
    memories: list[str] = Field(default_factory=list, max_length=2)
    music: Literal["tense", "calm", "warm", "quiet"] | None = None
    suggestions: list[ReplyOption] = Field(default_factory=list, max_length=3)
    moment: StoryMoment | None = None
    object_quotes: list[ObjectQuote] = Field(default_factory=list, max_length=3)
    image: str | None = Field(default=None, max_length=240)
    line: str = Field(min_length=1, max_length=1600)
    video_line: str = Field(default="", max_length=30)
    video_label: str = Field(default="看看回应时的神情", max_length=40)
    expression: str = Field(max_length=240)
    attention: str | None = None
    duration: Literal[4, 5, 6]


class Playback(BaseModel):
    turn: int
    phase: Literal["start", "end"]


class SceneWorld:
    def __init__(self, setting: SceneSetting, assets: dict) -> None:
        self.setting = setting
        self.assets = assets
        self.positions = {obj.id: 0 for obj in setting.objects}
        self.inspected = set()
        self.reactions = {obj.id for obj in setting.objects if obj.notice}
        self.leads = {obj.id: obj.lead.model_dump() for obj in setting.objects}
        self.movable = {obj.id: obj.id in assets["objects"] for obj in setting.objects}
        self.position_verified = True
        self.appearance = "Keep the opening pose and clothing unless the current object states specify a change."
        self.object_states = {obj.id: ObjectState(id=obj.id, description=obj.description,
                                                location="开场画面中的位置", visible=True, visual=obj.visual) for obj in setting.objects}

    def apply(self, reply: SceneReply) -> None:
        ids = [obj.id for obj in reply.object_updates]
        if len(ids) != len(set(ids)) or set(ids) - self.object_states.keys():
            raise ValueError("Object state update has duplicate or unknown IDs")
        self.object_states.update({obj.id: obj.model_copy() for obj in reply.object_updates})
        for key in ids:
            self.positions[key] = 0
            self.inspected.discard(key)
        if reply.appearance is not None:
            self.appearance = reply.appearance

    def snapshot(self) -> dict:
        return {"title": self.setting.title, "character": self.setting.character, "appearance": self.appearance,
                "objects": [{**self.object_states[obj.id].model_dump(), "name": obj.name,
                             "contents": obj.contents if obj.id in self.inspected else "",
                             "lead": copy.deepcopy(self.leads[obj.id]),
                             "dx": self.positions[obj.id], "inspected": obj.id in self.inspected,
                             "inspect_ready": obj.id not in self.inspected or obj.id in self.reactions,
                             "movable": self.movable[obj.id] and self.object_states[obj.id].visible,
                             "position_verified": self.position_verified and self.object_states[obj.id].visible
                             and (obj.id in self.assets["regions"] or obj.id in self.assets["objects"])}
                            for obj in self.setting.objects]}

    def choices(self) -> list[dict]:
        return [{"object": obj.id, "kind": "move", "target": obj.id, "delta": delta, "label": label}
                for obj in self.setting.objects for delta, label in [(-16, "向左挪一点"), (16, "向右挪一点")]
                if self.position_verified and self.object_states[obj.id].visible and self.movable[obj.id]
                and obj.id in self.assets["objects"] and min(self.assets["objects"][obj.id]["min_dx"], self.positions[obj.id])
                <= self.positions[obj.id] + delta <= max(self.assets["objects"][obj.id]["max_dx"], self.positions[obj.id])]

    def perform(self, action: Action, actor: str = "你") -> str:
        if action.kind == "talk":
            if not action.text.strip():
                raise ValueError("先写下你想说的话。")
            return action.text.strip()
        if action.kind == "wait":
            return f"暂时停下，留意{self.setting.character}的反应。"
        obj = next((obj for obj in self.setting.objects if obj.id == action.target), None)
        if obj is None:
            raise ValueError("请先选择场景里的一件物品。")
        if action.kind == "inspect":
            self.inspected.add(obj.id)
            self.reactions.discard(obj.id)
            state = self.object_states[obj.id]
            return state.description + ("\n所在位置：" + state.location if state.location != "开场画面中的位置" else "") + ("\n查看内容：" + obj.contents if obj.contents else "")
        if action.kind != "move" or not any(c["target"] == action.target and c["delta"] == action.delta for c in self.choices()):
            raise ValueError("现在无法这样移动，请按当前画面选择操作。")
        self.positions[obj.id] += action.delta
        polygon = self.assets["initial"]["objects"][obj.id]["polygon"]
        x = (min(p[0] for p in polygon) + max(p[0] for p in polygon)) / 2 + self.positions[obj.id]
        y = (min(p[1] for p in polygon) + max(p[1] for p in polygon)) / 2 + self.positions[obj.id] * self.assets["objects"][obj.id]["slope"]
        self.object_states[obj.id].location = f"原支撑面上，画面672×384中中心约({x:.0f}, {y:.0f})像素"
        self.object_states[obj.id].visual = f"The existing movable tabletop object remains on its support surface, centered near pixel ({x:.0f}, {y:.0f}) in the 672x384 frame. Preserve its size and shape."
        return f"{actor}把{obj.name}向画面{'左' if action.delta < 0 else '右'}侧挪了一点。"


@dataclass
class CrateWorld:
    crate_dx: int = 0
    min_dx: int = -96
    max_dx: int = 96
    slope: float = 0
    npc_actions: bool = True

    def snapshot(self) -> dict:
        return {"scene": "雨夜酒馆，人物已经松开箱子，箱子放在桌面上。",
                "objects": ["木箱（账册在箱内）", "Cassian"], "crate_dx": self.crate_dx,
                "crate_dy": round(self.crate_dx * self.slope),
                "position": "相对进入时的位置，单位像素；沿桌面移动，正数向右，纵向位移见 crate_dy。",
                "ledger": "inside_crate", "held": False,
                "interaction": "玩家可沿桌面挪木箱和交谈，没有取出账册或操作其他物品的能力。"
                + ("" if self.npc_actions else "Cassian 现在只交流、观察，不可移动箱子，也不可声称自己已经动过箱子。")}

    def choices(self) -> list[dict]:
        return [{"object": "crate", "kind": kind, "label": label}
                for kind, label, delta in [("crate_left", "向左挪", -32), ("crate_right", "向右挪", 32),
                                          ("crate_return", "放回原位", -self.crate_dx)]
                if delta and self.min_dx <= self.crate_dx + delta <= self.max_dx]

    def perform(self, action: Action, actor: str = "你") -> str:
        if action.kind == "talk":
            if not action.text.strip():
                raise ValueError("先写下你想说的话。")
            return action.text.strip()
        if action.kind == "wait":
            return "暂时停下手，看看 Cassian 会说什么。"
        if action.target or not any(c["kind"] == action.kind for c in self.choices()):
            raise ValueError("箱子已经到边了，请根据现在的位置选择动作。")
        match action.kind:
            case "crate_left":
                self.crate_dx -= 32
                movement = "向画面左侧挪了一点"
            case "crate_right":
                self.crate_dx += 32
                movement = "向画面右侧挪了一点"
            case "crate_return":
                self.crate_dx = 0
                movement = "放回了进入时的位置"
        return f"{actor}把木箱{movement}，里面的账册随箱子一起移动。"


@dataclass
class TavernWorld:
    bucket: str = "floor"
    crate: str = "wet"
    ledger: str = "crate"
    towels: dict = field(default_factory=lambda: {"towel_1": "dry", "towel_2": "dry"})
    puddle: bool = True

    @property
    def records_safe(self) -> bool:
        return self.ledger == "shelf" or self.crate == "safe"

    def snapshot(self) -> dict:
        return {**asdict(self), "leak_active": True, "records_safe": self.records_safe,
                "settled": self.bucket == "catch" and self.records_safe and not self.puddle}

    def choices(self) -> list[dict]:
        choices = [
            {"object": "bucket", "kind": "bucket_catch" if self.bucket == "floor" else "bucket_floor",
             "label": "放到漏水处接水" if self.bucket == "floor" else "把桶放回地上"},
            {"object": "crate", "kind": "crate_safe" if self.crate == "wet" else "crate_wet",
             "label": "把木箱搬到干处" if self.crate == "wet" else "把木箱搬回窗边"},
            {"object": "ledger", "kind": "ledger_safe" if self.ledger == "crate" else "ledger_crate",
             "label": "取出账册，放到干处" if self.ledger == "crate" else "把账册放回木箱"},
        ]
        for name, condition in self.towels.items():
            if self.puddle and condition != "wet":
                choices.append({"object": name, "kind": "wipe", "target": name, "label": "用这条毛巾擦水"})
            if condition == "wet":
                choices.append({"object": name, "kind": "wring", "target": name, "label": "把毛巾拧干一些"})
        return choices

    def perform(self, action: Action, actor: str = "你") -> str:
        if action.kind == "talk":
            if not action.text.strip():
                raise ValueError("先写下你想说的话。")
            return action.text.strip()
        if action.kind == "wait":
            return "暂时停下手，看看 Cassian 会做什么。"
        if not any(c["kind"] == action.kind and c.get("target", "") == action.target for c in self.choices()):
            raise ValueError("物品状态已经变化，请根据现在的场景选择动作。")
        if self.bucket != "catch":
            self.puddle = True
        match action.kind:
            case "bucket_catch":
                self.bucket = "catch"
                return f"{actor}把桶放到漏水处。水落进桶里，柜台上原有的积水还在。" if self.puddle else f"{actor}把桶放到漏水处，接住了落下的水。"
            case "bucket_floor":
                self.bucket = "floor"
                self.puddle = True
                return f"{actor}把桶放回地面。水又滴到了柜台上。"
            case "crate_safe":
                self.crate = "safe"
                return f"{actor}把木箱搬到干处。" + ("里面的账册也一起移走了。" if self.ledger == "crate" else "账册仍在原来的干处。")
            case "crate_wet":
                self.crate = "wet"
                return f"{actor}把木箱搬回窗边。" + ("账册也随箱子回到了窗边。" if self.ledger == "crate" else "账册仍单独留在干处。")
            case "ledger_safe":
                self.ledger = "shelf"
                return f"{actor}从箱里取出账册，单独放到干燥的柜台上。"
            case "ledger_crate":
                self.ledger = "crate"
                return f"{actor}把账册放回木箱里。"
            case "wipe":
                self.towels[action.target] = "wet"
                self.puddle = False
                return f"{actor}用{'第一' if action.target == 'towel_1' else '第二'}条毛巾擦掉积水，毛巾湿透了。" + ("漏水还没接住，之后仍会积水。" if self.bucket != "catch" else "柜台干净了，新的水滴落进桶里。")
            case "wring":
                self.towels[action.target] = "damp"
                return f"{actor}把毛巾拧得不再滴水。它仍然潮湿，但可以继续吸水。"
        raise ValueError("这个动作暂时无法执行。")
