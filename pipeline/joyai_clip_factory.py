"""JoyAIClipFactory:视频侧真实现,同 run(in_q,out_q,stop) 接口替换 StubClipFactory,编排层零改动。

复用官方常驻多卡 server(server/app.py,CUDA_VISIBLE_DEVICES=4,5,6,7 起 4 个常驻 GPU worker):
本类只做 HTTP 客户端 + 有序在飞窗口 + 烧字幕,不持有 GPU、不管权重生命周期。

为什么要窗口:单卡 ~39s 出一 9.64s 片,串行必落后播放。把最多 WINDOW(=卡数)条请求同时投给 server
(它自动分到空闲卡),再严格按投递顺序收最旧一条 —— 既并行占满 4 卡,又保证 ready_q 顺序 = 播放顺序。

烧字幕在收片后串行做(复用 SubtitleBurner,不重实现);其 re-encode 耗时由 smoke_joyai_clip 实测,
若成为瓶颈(> 单片播放预算)再挪进线程池 —— 先按最简证明"生成能跑在播放前面"。
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from collections import deque

import requests

from pipeline.clip_factory import PlayableClip
from pipeline.story_feed import ShotUnit
from subtitle_film import SubtitleBurner

JOYAI_URL = os.environ.get("JOYAI_URL", "http://127.0.0.1:8221")
WINDOW = 8            # 在飞并发 = server GPU worker 数(8 卡全放行)
POLL_INTERVAL = 2.0   # 轮询最旧一条的间隔(单片 ~39s,足够细)
CLIP_TIMEOUT = 300.0  # 单片兜底超时:超了判弃,别让一条卡死拖垮整流


class JoyAIClipFactory:
    def __init__(self, out_dir: str, base_url: str = JOYAI_URL, window: int = WINDOW,
                 burn_subtitles: bool = False):
        self.out_dir = out_dir
        self.base_url = base_url.rstrip("/")
        self.window = window
        self.burn_subtitles = burn_subtitles  # 默认关:语音已对口型念出,常驻烧字幕反而破坏沉浸
        self.burner = SubtitleBurner() if burn_subtitles else None
        self.session = requests.Session()
        self.inflight: deque[tuple[ShotUnit, str, float]] = deque()
        os.makedirs(out_dir, exist_ok=True)

    def run(self, in_q: queue.Queue, out_q: queue.Queue, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self._top_up(in_q)
                if not self.inflight:                       # 无在飞:阻塞等一个新请求,不空转
                    try:
                        self._submit(in_q.get(timeout=0.5))
                    except queue.Empty:
                        pass
                    continue
                unit, vid, t0 = self.inflight[0]            # 只收最旧一条 → 顺序 = 播放顺序
                info = self._poll(vid)
                match info["status"]:
                    case "succeeded":
                        self.inflight.popleft()
                        self._put(out_q, self._finish(unit, info), stop)
                    case "failed":
                        self.inflight.popleft()
                        print(f"[JoyAI] shot {unit.index} 生成失败,跳过: {info.get('error')}")
                    case _ if time.monotonic() - t0 > CLIP_TIMEOUT:
                        self.inflight.popleft()
                        print(f"[JoyAI] shot {unit.index} 超 {CLIP_TIMEOUT:.0f}s 未出片,跳过")
                    case _:
                        time.sleep(POLL_INTERVAL)            # 最旧仍在跑:歇一下,下轮再补投 + 再轮询
            except requests.RequestException as e:          # server 抖动(常见于加载权重时):等一下再来,别杀死 factory
                print(f"[JoyAI] server 暂不可达,{POLL_INTERVAL:.0f}s 后重试: {e}")
                time.sleep(POLL_INTERVAL)

    def _top_up(self, in_q: queue.Queue) -> None:
        while len(self.inflight) < self.window:             # 补满窗口:非阻塞地把队里请求投出去
            try:
                unit = in_q.get_nowait()
            except queue.Empty:
                return
            self._submit(unit)

    def _submit(self, unit: ShotUnit) -> None:
        r = self.session.post(f"{self.base_url}/r2v", json=unit.payload, timeout=30)
        r.raise_for_status()
        self.inflight.append((unit, r.json()["version_id"], time.monotonic()))

    def _poll(self, version_id: str) -> dict:
        r = self.session.get(f"{self.base_url}/version/{version_id}", timeout=30)
        r.raise_for_status()
        return r.json()

    def _finish(self, unit: ShotUnit, info: dict) -> PlayableClip:
        dst = os.path.join(self.out_dir, f"shot_{unit.index:03d}.mp4")
        raw = self._raw(info)
        if self.burn_subtitles:
            self.burner.burn(raw, unit.beats, dst)  # 复用:逐 beat 烧 `Who: line`,音频保真
        else:
            shutil.copyfile(raw, dst)               # 默认:server 干净片直接落地,不烧字幕
        said = " ".join(f'{b["who"]}: {b["line"]}' for b in unit.beats)
        return PlayableClip(unit.index, dst, said)

    def _raw(self, info: dict) -> str:
        result = info.get("result") or {}
        local = result.get("output_path") or info.get("output_path")
        if local and os.path.exists(local):                 # 同机同盘:直接读 server 落地的干净 mp4(无字幕),不走 HTTP
            return local
        url = info.get("video_url") or result.get("video_url")
        if not url:
            raise RuntimeError(f"succeeded 但无出片: version={info.get('version_id')}")
        dst = os.path.join(self.out_dir, f"raw_{info['version_id']}.mp4")
        with self.session.get(url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in resp.iter_content(1 << 16):
                    f.write(chunk)
        return dst

    @staticmethod
    def _put(out_q: queue.Queue, clip: PlayableClip, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                out_q.put(clip, timeout=0.5)
                return
            except queue.Full:
                continue
