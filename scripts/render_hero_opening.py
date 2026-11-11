"""出 hero 开场首拍一条片(走真实管线 payload),落地 + 抽 3 帧,给人看画面。

payload 来自 StoryFeed.advance(None)(和 web demo 开场完全同一条路径),提交 JoyAI /r2v 出片。
"""
import json
import os
import shutil
import subprocess
import sys
import time

import imageio_ffmpeg
import requests

sys.path.insert(0, "/mnt/local/sean/Ludens")
from pipeline.story_feed import StoryFeed

JOYAI = "http://127.0.0.1:8221"
CARDS = "/mnt/local/sean/Ludens/seed_cards.json"
OUT = "/mnt/local/sean/Ludens/research/out/hero_opening"
POLL, TIMEOUT = 2.0, 300.0


def _frame(ffmpeg: str, mp4: str, t: float) -> str:
    png = mp4.replace(".mp4", f"_t{t:g}.png")
    subprocess.run([ffmpeg, "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", png],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return png


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    cards = json.load(open(CARDS))
    card = next(c for c in cards if c["id"] == "hero")

    payload = StoryFeed(card).advance(None).payload
    print("=== 开场 prompt ===\n", payload["prompt"], "\n")
    print("memory_slots:", json.dumps(payload["memory_slots"], ensure_ascii=False), "\n")

    s = requests.Session()
    vid = s.post(f"{JOYAI}/r2v", json=payload, timeout=30).json()["version_id"]
    print("submitted:", vid)
    t0 = time.monotonic()
    while True:
        info = s.get(f"{JOYAI}/version/{vid}", timeout=30).json()
        match info["status"]:
            case "succeeded":
                break
            case "failed":
                raise RuntimeError(f"生成失败: {info.get('error')}")
            case _ if time.monotonic() - t0 > TIMEOUT:
                raise RuntimeError(f"超 {TIMEOUT:.0f}s 未出片")
            case st:
                print(f"{st} … {time.monotonic() - t0:.0f}s")
                time.sleep(POLL)

    raw = (info.get("result") or {}).get("output_path") or info.get("output_path")
    if not raw or not os.path.exists(raw):
        raise RuntimeError(f"succeeded 但无落地文件: {info}")
    dst = os.path.join(OUT, "opening.mp4")
    shutil.copyfile(raw, dst)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    frames = [_frame(ff, dst, t) for t in (0.2, 4.5, 9.0)]
    print(f"\n✅ DONE ({time.monotonic() - t0:.0f}s) → {dst}")
    for f in frames:
        print(" frame:", f)


if __name__ == "__main__":
    main()
