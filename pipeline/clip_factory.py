"""ClipFactory:视频侧。从 request 队列取 ShotUnit,出片(烧字幕),塞 ready 队列。

接口 = run(in_q, out_q, stop):两种实现同签名,LudensPipeline 只认接口、不认实现。
StubClipFactory —— 不吃 GPU:把一个占位 mp4 当假片映射到 clips 目录,验证队列/缓冲/连播链路。
真 JoyAI 常驻 worker pool = M1,同接口替换,编排层零改动。
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
from dataclasses import dataclass

from pipeline.story_feed import ShotUnit


@dataclass
class PlayableClip:
    index: int
    clip_path: str   # 烧完字幕的 mp4
    said: str        # 台词文本(前端备用;字幕已烧进视频)


class StubClipFactory:
    """不出真片:把 placeholder mp4 拷成 shot_XXX.mp4,秒出。验证链路不吃 GPU。"""

    def __init__(self, placeholder: str, out_dir: str):
        self.placeholder = placeholder
        self.out_dir = out_dir

    def run(self, in_q: queue.Queue, out_q: queue.Queue, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                unit: ShotUnit = in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            clip = self._fake(unit)
            while not stop.is_set():
                try:
                    out_q.put(clip, timeout=0.5)
                    break
                except queue.Full:
                    continue

    def _fake(self, unit: ShotUnit) -> PlayableClip:
        dst = os.path.join(self.out_dir, f"shot_{unit.index:03d}.mp4")
        shutil.copyfile(self.placeholder, dst)
        said = " ".join(f'{b["who"]}: {b["line"]}' for b in unit.beats)
        return PlayableClip(unit.index, dst, said)
