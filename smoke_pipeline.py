"""M3/M4 smoke:进程内跑 StoryFeed→StubClipFactory→ready_q 数据链,验证连播链路。不吃 GPU、不开端口。

daemon 线程 + stop.set() 收尾,无残留进程。HTTP 连播视觉留给浏览器(python -m pipeline.ludens_pipeline)。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pipeline.clip_factory import StubClipFactory  # noqa: E402
from pipeline.ludens_pipeline import LIVE_DIR, PLACEHOLDER, LudensPipeline  # noqa: E402

N = 4


def main():
    assert os.path.exists(PLACEHOLDER), f"placeholder missing: {PLACEHOLDER}"
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    denji = next(c for c in cards if c["id"] == "denji")

    pipe = LudensPipeline(denji, StubClipFactory(PLACEHOLDER, LIVE_DIR))
    pipe.start_workers()
    try:
        seen = []
        for _ in range(N):
            clip = pipe.ready_q.get(timeout=180)
            assert os.path.exists(clip.clip_path), clip.clip_path
            assert os.path.getsize(clip.clip_path) > 0, clip.clip_path
            seen.append(clip.index)
            print(f"[ready shot {clip.index}] {clip.clip_path}  ({os.path.getsize(clip.clip_path)//1024} KB)")
            print(f"  said: {clip.said[:80]}")
        assert seen == list(range(1, N + 1)), seen  # 顺序 1..N 无乱序无丢
        print(f"\nOK: {N} clips ready in order {seen}; app routes={[r.path for r in pipe.app.routes if hasattr(r,'path')]}")
    finally:
        pipe.stop.set()


if __name__ == "__main__":
    main()
