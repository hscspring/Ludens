"""Smoke:aim_data_sample.json 的每个 shot → ShotRenderer → R2V payload,过 r2v_schema 校验后落盘。

验证我们拼的 payload 是 JoyAI load_r2v_request 能吃的合法 R2V 请求(schema 全量校验),并盯 prompt 的 1500 硬上限。
纯 CPU,无 GPU、无推理。
"""
import json
import os
import sys

from shot_renderer import ShotRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "research", "aim_data_sample.json")
OUT_DIR = os.path.join(HERE, "research", "r2v_requests")
JOYAI = "/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo"

sys.path.insert(0, JOYAI)
from r2v_schema import normalize_r2v_payload  # noqa: E402  (纯标准库,scene_service 可 import)


def main():
    data = json.load(open(SAMPLE))
    os.makedirs(OUT_DIR, exist_ok=True)
    renderer = ShotRenderer(work_id=f"ludens-{data['card_id']}-demo")

    for shot in data["shots"]:
        payload = renderer.render(shot["index"], shot["turns"], shot["camera"])
        req = normalize_r2v_payload(payload, base_dir=OUT_DIR, resolve_resources=False)  # 抛=非法
        path = os.path.join(OUT_DIR, f"{payload['shot_id']}.json")
        json.dump(payload, open(path, "w"), ensure_ascii=False, indent=2)
        n = len(payload["prompt"])
        flag = "  <-- OVER 1500, WILL TRUNCATE" if n > 1500 else ""
        print(f"[{payload['shot_id']}] prompt={n} chars slots={len(req.memory_slots)} "
              f"ids={renderer.ids}{flag}")
        print(f"  {payload['prompt']}\n")

    print(f"saved {len(data['shots'])} R2V requests -> {OUT_DIR}")


if __name__ == "__main__":
    main()
