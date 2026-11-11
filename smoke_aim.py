"""Smoke:Denji 卡 → RosterExtractor(跨镜常量)+ ContentDirector(多 role 内容)+ CameraDirector(运镜),
连产 3 shot 落盘。

产出的 aim_data_sample.json 就是将来训 aim 的一条样本雏形:roster 常量 + 每 shot 的多 role messages
(state 轮场景规格 + assistant 轮分角色 beats)+ 运镜决策。纯 LLM 调用,无 GPU。
"""
import json
import os

from aim_directors import CameraDirector, ContentDirector, RosterExtractor
from llm_client import LLMClient

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "research", "aim_data_sample.json")


def main():
    cards = json.load(open(os.path.join(HERE, "seed_cards.json")))
    denji = next(c for c in cards if c["id"] == "denji")
    llm = LLMClient()

    roster = RosterExtractor(llm, denji).extract()
    content = ContentDirector(llm, denji, roster)
    camera = CameraDirector(llm)

    shots, history = [], []
    for i in range(1, 4):
        turns = content.next_shot(history)
        camera_out = camera.next_scene(turns)
        shots.append({"index": i, "turns": turns, "camera": camera_out})
        history.append(turns)

    data = {"card_id": denji["id"], "roster": roster, "shots": shots}
    json.dump(data, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
