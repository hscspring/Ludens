"""单片客户端 smoke:验证 JoyAI HTTP 全链路(POST /r2v → 轮询 → 取回干净 mp4 → 烧字幕 → 有音有视)。

需 server 已在跑(用户先跑 ./start_joyai_server.sh);Claude 不起 server。

顺带:
  - 暴露 D2 风险 —— 空 memory_slots 是否被引擎接受(被拒会打印 server 的 error)。
  - 实测两项耗时 gen_secs / burn_secs,判断烧字幕会不会成为"落后播放"的瓶颈。
"""
import json
import os
import sys
import time

import av

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from pipeline.joyai_clip_factory import JoyAIClipFactory  # noqa: E402
from pipeline.story_feed import MAX_RETRY, StoryFeed  # noqa: E402

OUT = os.path.join(HERE, "research", "out", "joyai_smoke")


def one_unit() -> "ShotUnit":  # noqa: F821
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    denji = next(c for c in cards if c["id"] == "denji")
    feed = StoryFeed(denji)
    for _ in range(MAX_RETRY):
        try:
            return feed.advance()
        except (ValueError, RuntimeError) as e:
            print(f"  (内容重产: {e})"[:100])
    raise RuntimeError("denji 连 MAX_RETRY 次坏输出,内容侧问题,与 JoyAI 无关")


def probe(path: str) -> tuple[tuple[int, int], float, bool]:
    c = av.open(path)
    v = c.streams.video[0]
    has_audio = len(c.streams.audio) > 0
    dims, dur = (v.width, v.height), float(c.duration or 0) / 1e6
    c.close()
    return dims, dur, has_audio


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    f = JoyAIClipFactory(out_dir=OUT)
    print(f"server = {f.base_url}  (memory_slots 空 = 纯 prompt 弱锁,验 D2)")

    unit = one_unit()
    print(f"shot {unit.index}: prompt={len(unit.payload['prompt'])} "
          f"slots={len(unit.payload['memory_slots'])} beats={len(unit.beats)}")

    t0 = time.monotonic()
    f._submit(unit)
    _, vid, _ = f.inflight[0]
    print(f"version_id={vid}  轮询中…")
    while True:
        info = f._poll(vid)
        el = time.monotonic() - t0
        if info["status"] in {"succeeded", "failed"}:
            print(f"  [{el:5.1f}s] {info['status']}")
            break
        print(f"  [{el:5.1f}s] {info['status']}/{info.get('stage')}")
        time.sleep(3)
    assert info["status"] == "succeeded", \
        f"生成失败(重点看是不是空 memory_slots 被拒): {info.get('error')}"
    gen = time.monotonic() - t0

    f.inflight.popleft()
    tb = time.monotonic()
    clip = f._finish(unit, info)
    burn = time.monotonic() - tb

    assert os.path.exists(clip.clip_path) and os.path.getsize(clip.clip_path) > 0, clip.clip_path
    dims, dur, has_audio = probe(clip.clip_path)
    assert has_audio, "出片无音轨"

    budget = unit.payload["duration_sec"]
    print(f"\nOK  gen={gen:.1f}s  burn={burn:.1f}s  dims={dims}  dur={dur:.2f}s  audio={has_audio}")
    print(f"    片 = {clip.clip_path}")
    print(f"    said = {clip.said[:80]}")
    print(f"\n预算判读: 单片播放 {budget:.2f}s;4 卡并行有效产片 ≈ gen/4 = {gen / 4:.1f}s;烧字幕 {burn:.1f}s(串行)")
    if burn > budget:
        print("  ⚠ 烧字幕 > 单片播放预算 → 串行烧录是瓶颈,需挪进线程池(M1 后续)")
    if gen / 4 > budget:
        print("  ⚠ 即便 4 卡并行,单片生成仍 > 播放预算 → 需更多卡或降 num_frames/steps")


if __name__ == "__main__":
    main()
