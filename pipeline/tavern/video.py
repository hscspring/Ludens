from __future__ import annotations

import json
import logging
import math
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from PIL import Image

if TYPE_CHECKING:
    from pipeline.tavern.api import TavernSession

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger(__name__)


class SceneVideo:
    def __init__(self, root: Path, assets: dict, config: dict) -> None:
        self.root = root
        self.assets = assets
        self.assets["initial"]["slopes"] = {key: obj["slope"] for key, obj in assets["objects"].items()}
        self.config = config
        self.ffmpeg = ROOT / config["ffmpeg"]
        self.jobs = queue.Queue()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, session: TavernSession, seq: int) -> None:
        self.jobs.put((session, seq))

    def _work(self) -> None:
        while True:
            session, seq = self.jobs.get()
            try:
                session.render_video(seq)
            except (requests.RequestException, ValueError, RuntimeError, OSError, KeyError, subprocess.CalledProcessError):
                LOG.exception("Event video failed for %s:%s", session.id, seq)
                session.fail_video(seq)
            finally:
                self.jobs.task_done()

    def compose(self, visual: dict, positions: dict, output: Path) -> None:
        deltas = {key: positions[key] - visual["positions"][key] for key in visual["objects"]}
        if not any(deltas.values()):
            Image.open(visual["frame"]).save(output)
            return
        background = Image.open(visual["background"]).convert("RGBA")
        for key, delta in deltas.items():
            sprite = Image.open(visual["objects"][key]["sprite"]).convert("RGBA")
            background.alpha_composite(sprite, (delta, round(delta * visual["slopes"][key])))
        background.convert("RGB").save(output)

    def generate(self, reference: Path, line: str, expression: str, duration: int, folder: Path, music: str = "quiet") -> dict:
        line = line.strip()
        if line:
            duration = max(duration, min(15, math.ceil(sum(char.isalnum() for char in line) / 3.5 + 1.5)))
        speech = (f"The character speaks EXACTLY these words ONCE in Mandarin Chinese, with {self.config['voice']}: "
                  f"{json.dumps(line, ensure_ascii=False)}. Start promptly and say the complete sentence naturally. "
                  "No added words, paraphrasing or filler speech. Finish the last word before settling quietly. "
                  if line else "NO human speech, whispers, humming or vocal sounds. Lips stay closed throughout this silent reaction. ")
        prompt = (
            "Continue this exact reference frame. Locked tripod camera, same framing, same person, face, voice and clothes. "
            "Preserve the reference art style, linework and shading; never turn an illustrated character into a real person. "
            "Keep all objects exactly in place and unchanged. Both hands stay away from the objects; no reaching, lifting, turning or walking. "
            f"The character {expression}. {speech} "
            "End in a quiet attentive expression, mouth closed, hands still. "
            f"{self.config.get('ambience', 'Quiet rain ambience')}, no music, no subtitles or text. No other speaker."
        )
        data = {"prompt": prompt, "width": self.assets["width"], "height": self.assets["height"],
                "fps": 24, "seed": 7, "num_inference_steps": 8, "flow_shift": 12,
                "extra_params": json.dumps({"task": "fl2va", "duration": duration, "audio_flow_shift": 3.0}),
                "lora": json.dumps({"name": "h3-turbo8", "path": self.config["lora"], "scale": 1.0})}
        started = time.monotonic()
        with reference.open("rb") as source:
            response = requests.post(self.config["url"].rstrip("/") + "/v1/videos/sync", data=data,
                                     files={"input_reference": ("reference.png", source, "image/png")}, timeout=240)
        response.raise_for_status()
        (folder / "original.mp4").write_bytes(response.content)
        soundtrack = ROOT / "pipeline/tavern/static/roleplay/audio" / f"{music}.mp3" if music in {"tense", "calm", "warm"} else None
        audio = ["-c:a", "aac", "-b:a", "64k"] if line or soundtrack else ["-an"]
        self._encode(folder / "original.mp4", folder / "play.mp4", ["-vf", "scale=640:-2,setsar=1,fps=16", *audio],
                     soundtrack, bool(line))
        last_frame = folder / "last_frame.png"
        self.last_frame(folder / "play.mp4", last_frame)
        result = {"video": str(folder / "play.mp4"),
                  "seconds": round(time.monotonic() - started, 2), "duration": duration, "last_frame": str(last_frame),
                  "music": music if soundtrack else "quiet"}
        (folder / "generation.json").write_text(json.dumps({**data, **result}, ensure_ascii=False, indent=2))
        return result

    def last_frame(self, source: Path, output: Path) -> None:
        subprocess.run([str(self.ffmpeg), "-nostdin", "-n", "-loglevel", "error", "-sseof", "-1", "-i", str(source),
                        "-vf", "reverse", "-frames:v", "1", str(output)], check=True, capture_output=True)

    def public_visual(self, visual: dict) -> dict:
        return {**visual, "frame": self.url(visual["frame"]), "background": self.url(visual["background"]),
                "idle": self.url(visual["idle"]) if visual.get("idle") else None,
                "objects": {key: {**obj, "sprite": self.url(obj["sprite"])} for key, obj in visual["objects"].items()}}

    def url(self, path: str | Path) -> str:
        return "/live-assets/" + str(Path(path).relative_to(self.root / "media"))

    def _encode(self, source: Path, output: Path, filters: list[str], soundtrack: Path | None = None, speech: bool = True) -> None:
        audio = []
        if soundtrack:
            mix = "[1:a]volume=0.22[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[music]" if speech else "[1:a]volume=0.22[music]"
            audio = ["-stream_loop", "-1", "-i", str(soundtrack), "-filter_complex", mix,
                     "-map", "0:v:0", "-map", "[music]", "-shortest"]
        subprocess.run([str(self.ffmpeg), "-nostdin", "-n", "-loglevel", "error", "-i", str(source),
                        *audio, *filters, "-c:v", "libx264", "-threads", "4", "-crf", "27", "-maxrate", "500k",
                        "-bufsize", "1000k", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)],
                       check=True, capture_output=True)
