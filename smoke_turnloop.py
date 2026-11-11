"""纯 CPU 逻辑 smoke:验证回合制接线,不碰 LLM/GPU。
换掉 StoryFeed 依赖的三个 director + renderer 为假实现,只测 run(input_q, request_q, stop) 的驱动语义:
开场自动产一拍(user_turn=None)→ 阻塞 → 每条玩家输入产下一拍且 user_turn 原样透传。"""
import queue
import threading
import time

import pipeline.story_feed as sf


class FakeContent:
    def __init__(self, *a, **k):
        self.seen = []  # 记录每拍收到的 user_turn,回头核对透传

    def next_shot(self, history, user_turn=None):
        self.seen.append(user_turn)
        turns = [{"role": "state", "content": {"location": "loft", "characters": {"Denji": {}}}},
                 {"role": "assistant", "content": {"beats": [{"who": "Denji", "line": "hi", "action": "nods"}]}}]
        if user_turn:
            turns.insert(0, {"role": "user", "content": user_turn})
        return turns


class FakeCamera:
    def __init__(self, *a, **k): ...
    def next_scene(self, turns): return {"shot_size": "medium", "camera_move": "static", "environment": "dim"}


class FakeRenderer:
    def __init__(self, *a, **k): ...
    def render(self, index, turns, camera): return {"shot_id": f"shot_{index:03d}"}


class FakeRoster:
    def __init__(self, *a, **k): ...
    def extract(self): return {"Denji": {"appearance": "spiky hair", "voice": "brash tenor"}}


sf.ContentDirector, sf.CameraDirector, sf.ShotRenderer, sf.RosterExtractor = (
    FakeContent, FakeCamera, FakeRenderer, FakeRoster)

card = {"id": "denji", "welcome": "You wake in the loft.", "system": "[Character Card]\nDenji\nuser_profile:", "lang": "en"}
feed = sf.StoryFeed(card)
in_q: queue.Queue = queue.Queue(maxsize=4)
out_q: queue.Queue = queue.Queue(maxsize=6)
stop = threading.Event()
threading.Thread(target=feed.run, args=(in_q, out_q, stop), daemon=True).start()

opening = out_q.get(timeout=5)                       # 开场:必须自动出第 1 拍,无需任何输入
assert opening.index == 1, opening.index
time.sleep(0.3)
assert out_q.empty(), "开场后应阻塞等输入,不该自动产第 2 拍"

in_q.put("我拔出剑,冷冷问他你是谁")                    # 玩家这拍输入 → 应产第 2 拍
shot2 = out_q.get(timeout=5)
assert shot2.index == 2, shot2.index
time.sleep(0.3)
assert out_q.empty(), "第 2 拍后应再次阻塞等输入"

in_q.put("我转身走向门口")
shot3 = out_q.get(timeout=5)
assert shot3.index == 3, shot3.index

seen = feed.content.seen
assert seen == [None, "我拔出剑,冷冷问他你是谁", "我转身走向门口"], seen  # user_turn 逐拍原样透传
assert any(t["role"] == "user" and t["content"] == "我拔出剑,冷冷问他你是谁" for t in shot2.turns), "user 轮未进 history"

stop.set()
print("TURNLOOP_SMOKE_OK  shots:", opening.index, shot2.index, shot3.index, " seen:", seen)
