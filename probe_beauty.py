"""一次性探针:量 JoyAI-Echo 的画面精美度天花板,跟叙事/选卡解耦。

喂一张 p.mp4 级半写实美图,出一条安静的单人竖屏片,看模型动起来后画质保不保得住。
同一 prompt/seed/尺寸,唯一变量 = 怎么喂图:
  condimg  — condition_img 首帧锚(整幅画面继承),现管线没验过的路径
  memslot  — memory_slots.image_url 外形强锚(the_last_visa 验过的路径),prompt 引用 ID_A
  prompt   — 无图纯文字,对照组:没有美图锚时模型自己能到什么水平
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time

import requests
import imageio_ffmpeg

JOYAI_URL = "http://127.0.0.1:8221"
SCHEMA_PY = "/mnt/local/sean/wm_repos/JoyAI-Echo/echo_longvideo/r2v_schema.py"
OUT_DIR = "/mnt/local/sean/Ludens/research/out/beauty_probe"
DEFAULT_REF = "/tmp/p_t8.png"
POLL, TIMEOUT = 2.0, 300.0

STYLE = ("Semi-realistic painterly anime art style, cinematic volumetric lighting, "
         "highly detailed skin and hair, shallow depth of field.")
SCENE = ("stands against a dark brick wall in moody blue light, breathes softly, "
         "tilts his head slightly and looks directly at the camera with a subtle expression. "
         "Close-up portrait, static camera.")
SUBJECT_PROMPT = f"A single handsome young man with blond hair and glowing amber eyes {SCENE}"
SUBJECT_IDA = f"ID_A is a handsome young man with blond hair and glowing amber eyes. ID_A {SCENE}"
NEG = " No subtitles, captions, on-screen text, or writing."


def _load_schema():
    spec = importlib.util.spec_from_file_location("r2v_schema", SCHEMA_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["r2v_schema"] = mod  # dataclass frozen 处理需从 sys.modules 反查本模块
    spec.loader.exec_module(mod)
    return mod


class BeautyProbe:
    def __init__(self, ref: str):
        self.ref = os.path.abspath(ref)
        self.schema = _load_schema()
        self.session = requests.Session()
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        os.makedirs(OUT_DIR, exist_ok=True)

    def payload(self, variant: str) -> dict:
        p = {"work_id": "beauty_probe", "shot_id": f"probe_{variant}",
             "condition_img": None, "memory_slots": [],
             "num_frames": 241, "width": 736, "height": 1280,
             "seed": 42, "duration_sec": 9.64}
        match variant:
            case "condimg":
                p["prompt"] = STYLE + " " + SUBJECT_PROMPT + NEG
                p["condition_img"] = self.ref
            case "memslot":
                p["prompt"] = STYLE + " " + SUBJECT_IDA + NEG
                p["memory_slots"] = [{"image_url": self.ref, "metadata": {"id": "ID_A"}}]
            case "prompt":
                p["prompt"] = STYLE + " " + SUBJECT_PROMPT + NEG
            case _:
                raise ValueError(f"unknown variant {variant}")
        self.schema.normalize_r2v_payload(p, resolve_resources=False)  # fail-fast 契约校验
        return p

    def run(self, variant: str) -> str:
        payload = self.payload(variant)
        print(f"[{variant}] submit → {self.ref if payload['condition_img'] or payload['memory_slots'] else '(no image)'}")
        r = self.session.post(f"{JOYAI_URL}/r2v", json=payload, timeout=30)
        r.raise_for_status()
        vid = r.json()["version_id"]
        info = self._wait(variant, vid)
        raw = (info.get("result") or {}).get("output_path") or info.get("output_path")
        if not raw or not os.path.exists(raw):
            raise RuntimeError(f"[{variant}] succeeded 但无落地文件: {info}")
        dst = os.path.join(OUT_DIR, f"{variant}.mp4")
        shutil.copyfile(raw, dst)
        for t in (0.2, 4.5, 9.0):
            self._frame(dst, t)
        print(f"[{variant}] DONE → {dst}")
        return dst

    def _wait(self, variant: str, vid: str) -> dict:
        t0 = time.monotonic()
        while True:
            info = self.session.get(f"{JOYAI_URL}/version/{vid}", timeout=30).json()
            match info["status"]:
                case "succeeded":
                    return info
                case "failed":
                    raise RuntimeError(f"[{variant}] 生成失败: {info.get('error')}")
                case _ if time.monotonic() - t0 > TIMEOUT:
                    raise RuntimeError(f"[{variant}] 超 {TIMEOUT:.0f}s 未出片")
                case st:
                    print(f"[{variant}] {st} … {time.monotonic() - t0:.0f}s")
                    time.sleep(POLL)

    def _frame(self, mp4: str, t: float) -> None:
        png = mp4.replace(".mp4", f"_t{t:g}.png")
        subprocess.run([self.ffmpeg, "-y", "-ss", str(t), "-i", mp4,
                        "-frames:v", "1", png], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    variants = sys.argv[1].split(",") if len(sys.argv) > 1 else ["condimg", "memslot", "prompt"]
    ref = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REF
    probe = BeautyProbe(ref)
    results = {}
    for v in variants:
        try:
            results[v] = probe.run(v)
        except (requests.RequestException, RuntimeError, ValueError) as e:  # 各路独立成败,都是探针结论
            results[v] = f"FAIL: {e}"
            print(f"[{v}] {results[v]}")
    print("\n=== 汇总 ===")
    for v, r in results.items():
        print(f"{v}: {r}")


if __name__ == "__main__":
    main()
