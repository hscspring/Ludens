"""连续性吞吐 smoke:量"生成能否跑在播放前面"。

真流水线形状(共享一条 StoryFeed + JoyAIClipFactory + 两个 bounded queue,window=4 卡),
连产 n 片,记录每片就绪时刻。前 4 片各含一次冷加载(每卡首片载权重),看第 5 片起的
稳态到达间隔:若 < 单片播放预算(9.66s)→ 4 卡并行能持续领先播放,连播不断流。

需 server 已在跑(./start_joyai_server.sh)。main() 只实例化 + 调用。
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402

sys.path.insert(0, HERE)

from pipeline.joyai_clip_factory import JoyAIClipFactory  # noqa: E402
from pipeline.story_feed import MAX_RETRY, StoryFeed  # noqa: E402

OUT = os.path.join(HERE, "research", "out", "joyai_throughput")
Q_MAX = 3


class ThroughputSmoke:
    def __init__(self, card: dict, n: int):
        self.feed = StoryFeed(card)
        self.factory = JoyAIClipFactory(out_dir=OUT)
        self.n = n
        self.request_q: queue.Queue = queue.Queue(maxsize=Q_MAX)
        self.ready_q: queue.Queue = queue.Queue(maxsize=Q_MAX)
        self.stop = threading.Event()

    def _produce(self) -> None:
        made = 0
        while made < self.n and not self.stop.is_set():
            for _ in range(MAX_RETRY):
                try:
                    unit = self.feed.advance()
                    break
                except (ValueError, RuntimeError) as e:
                    print(f"  (shot {made + 1} 内容重产: {e})"[:90])
            else:
                raise RuntimeError(f"shot {made + 1} 连 {MAX_RETRY} 次坏内容,与 JoyAI 无关")
            self.request_q.put(unit)
            made += 1

    def run(self) -> None:
        budget = None
        threading.Thread(target=self._produce, daemon=True).start()
        threading.Thread(target=self.factory.run,
                         args=(self.request_q, self.ready_q, self.stop), daemon=True).start()
        budget = 9.66
        t0 = time.monotonic()
        readies: list[float] = []
        for _ in range(self.n):
            clip = self.ready_q.get()
            t = time.monotonic() - t0
            gap = t - readies[-1] if readies else t
            readies.append(t)
            print(f"shot {clip.index:2d} ready @ {t:6.1f}s  (逐片间隔 {gap:5.1f}s)  {clip.said[:48]}")
        self.stop.set()

        # window=4:前 4 片各含一次冷加载 → 摊销有效间隔只算窗口填满后的暖批(第 5 片起整批墙钟 ÷ 片数)。
        print(f"\n单片播放预算 = {budget:.2f}s")
        if self.n > self.factory.window:
            warm_wall = readies[-1] - readies[self.factory.window - 1]
            warm_n = self.n - self.factory.window
            eff = warm_wall / warm_n
            print(f"摊销有效间隔(暖态,{warm_n} 片 / {warm_wall:.1f}s)= {eff:.1f}s/片")
            verdict = "✅ 生成领先播放,连播不断流" if eff < budget else \
                f"⚠ 生成落后播放(需 ≥{eff / budget:.1f}× 卡数,或降 num_frames/steps)"
            print(verdict)
        else:
            print("n 未超窗口,无暖态样本,仅看上面逐片间隔")


def main() -> None:
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    denji = next(c for c in cards if c["id"] == "denji")
    os.makedirs(OUT, exist_ok=True)
    ThroughputSmoke(denji, n=8).run()


if __name__ == "__main__":
    main()
