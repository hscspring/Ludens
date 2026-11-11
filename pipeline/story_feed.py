"""StoryFeed:内容侧,自动把一个故事往前推,持续产出下一 shot 的可播单元(剧情 + R2V payload)。

把 smoke_aim 里"手动跑 N 次 director"的 for 循环收成一个常驻类:advance(user_turn) 产一个 shot;
run() 被玩家输入队列驱动:开场先产一拍(用 welcome 建场景),之后每条玩家输入产下一拍——
回合制,剧情随玩家走。复用 RosterExtractor/ContentDirector/CameraDirector/ShotRenderer,不拆不重写。
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from aim_directors import CameraDirector, ContentDirector, RosterExtractor
from llm_client import LLMClient
from shot_renderer import ShotRenderer

MAX_RETRY = 5  # 连续 N 次 advance 失败才真抛;gemini 偶发坏输出(空 characters 等)靠重产兜


@dataclass
class ShotUnit:
    index: int
    turns: list[dict]   # [{role:state,...}, {role:assistant,...}]
    camera: dict
    beats: list[dict]   # assistant 轮的 beats,直接给 SubtitleBurner
    payload: dict       # R2V 请求,给 ClipFactory 出片


class StoryFeed:
    def __init__(self, card: dict, llm: LLMClient | None = None, work_id: str | None = None):
        self.llm = llm or LLMClient()
        self.opening_image = card.get("opening_image")
        roster = RosterExtractor(self.llm, card).extract()  # 跨镜常量,一次抽定
        self.content = ContentDirector(self.llm, card, roster)
        self.camera = CameraDirector(self.llm)
        self.renderer = ShotRenderer(work_id=work_id or f"ludens-{card['id']}-demo",
                                     assets=card.get("assets"),
                                     width=card.get("width", 1280),
                                     height=card.get("height", 736),
                                     style=card.get("style", "anime"),
                                     grade=card.get("grade", ""))
        self.history: list[list[dict]] = []
        self.index = 0

    def advance(self, user_turn: str | None = None) -> ShotUnit:
        turns = self.content.next_shot(self.history, user_turn)
        camera = self.camera.next_scene(turns)
        idx = self.index + 1
        payload = self.renderer.render(idx, turns, camera)
        if idx == 1:
            payload["condition_img"] = self.opening_image
        self.history.append(turns)  # index/history 只在成功产出后推进,中途抛不留半条状态
        self.index = idx
        beats = next(t["content"]["beats"] for t in turns if t["role"] == "assistant")
        return ShotUnit(idx, turns, camera, beats, payload)

    def run(self, in_q: queue.Queue, out_q: queue.Queue, stop: threading.Event) -> None:
        self._advance_put(None, out_q, stop)                  # 开场:无输入先产第一拍
        while not stop.is_set():
            try:
                user_turn = in_q.get(timeout=0.5)             # 回合制:等玩家这拍输入才产下一拍
            except queue.Empty:
                continue
            self._advance_put(user_turn, out_q, stop)

    def _advance_put(self, user_turn: str | None, out_q: queue.Queue, stop: threading.Event) -> None:
        fails = 0
        while not stop.is_set():
            try:
                unit = self.advance(user_turn)
                break
            except (ValueError, RuntimeError) as e:  # LLM 偶发坏输出/端点全挂:重产该 shot,别杀死 feed
                fails += 1
                print(f"[StoryFeed] shot {self.index + 1} 重产 ({fails}/{MAX_RETRY}): {e}")
                if fails >= MAX_RETRY:
                    raise
        else:
            return
        while not stop.is_set():
            try:
                out_q.put(unit, timeout=0.5)
                return
            except queue.Full:
                continue
