"""M2 smoke:StoryFeed 连产 N 个 shot,验证 payload 过 schema + history 累积 + 剧情推进。纯 LLM,无 GPU。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo")

from pipeline.story_feed import StoryFeed  # noqa: E402
from r2v_schema import normalize_r2v_payload  # noqa: E402  (纯标准库)

N = 5


def main():
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    denji = next(c for c in cards if c["id"] == "denji")
    feed = StoryFeed(denji)

    for _ in range(N):
        unit = feed.advance()
        normalize_r2v_payload(unit.payload, base_dir=HERE, resolve_resources=False)  # 抛=非法
        loc = next(t["content"]["location"] for t in unit.turns if t["role"] == "state")
        said = " ".join(f'{b["who"]}: "{b["line"]}"' for b in unit.beats)
        n = len(unit.payload["prompt"])
        flag = "  <-- OVER 1500" if n > 1500 else ""
        print(f"[shot {unit.index} @ {loc}] prompt={n} chars beats={len(unit.beats)}{flag}")
        print(f"  {said}")

    assert len(feed.history) == N, len(feed.history)
    assert feed.index == N, feed.index
    print(f"\nOK: {N} shots, history={len(feed.history)}, ids={feed.renderer.ids}")


if __name__ == "__main__":
    main()
