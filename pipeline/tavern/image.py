from __future__ import annotations

import base64
import io
import logging
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from PIL import Image

from llm_client import ENDPOINTS, LLMClient
from pipeline.tavern.layout import SceneLayout

if TYPE_CHECKING:
    from pipeline.tavern.api import TavernSession

LOG = logging.getLogger(__name__)


class SceneImage:
    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.layout = SceneLayout(LLMClient(endpoints=[ENDPOINTS[0]]), url)
        self.jobs = queue.Queue()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, session: TavernSession, seq: int) -> None:
        self.jobs.put((session, seq))

    def _work(self) -> None:
        while True:
            session, seq = self.jobs.get()
            try:
                session.render_image(seq)
            except (requests.RequestException, ValueError, RuntimeError, OSError, KeyError, TypeError):
                LOG.exception("Character image failed for %s:%s", session.id, seq)
                session.fail_image(seq)
            finally:
                self.jobs.task_done()

    def generate(self, reference: Path, expression: str, folder: Path, world: dict | None = None) -> Path:
        prompt = (
            "Edit this original scene into the following single moment. "
            f"Expression or gesture: {expression}. "
            "Preserve the exact facial proportions, eye and nose shapes, lip thickness, jaw contour and hair. "
            "Keep the original fine shading, skin texture and illustration style. Subtle facial movement, no exaggerated smile. "
            "Keep the camera, room, lighting and unchanged details. No text, captions, symbols or extra people. "
            "Apply these current physical states instead of the opening state: "
            + (world.get("appearance", "") + " " + " ".join(obj.get("visual", "") for obj in world["objects"]) if world else "No physical changes.")
        )
        edited = self._edit(reference, prompt)
        output = folder / "expression.webp"
        edited.save(output, lossless=True)
        return output

    def prepare(self, path: Path, objects: list[dict], expected: str, folder: Path, reference: Path | None = None,
                on_located: Callable[[dict], None] | None = None) -> dict:
        with Image.open(path) as image:
            frame = image.convert("RGB").resize((672, 384), Image.Resampling.LANCZOS)
        original = None
        if reference is not None:
            with Image.open(reference) as image:
                original = image.convert("RGB").resize((672, 384), Image.Resampling.LANCZOS)
        grounded = self.layout.locate(frame, objects, expected, original)
        if sorted(obj["id"] for obj in grounded["objects"]) != sorted(obj["id"] for obj in objects):
            raise ValueError("Scene recognition changed object identities")
        required = {obj["id"] for obj in objects if obj.get("visible", obj.get("position_verified"))}
        hidden = {obj["id"] for obj in objects if obj.get("visible") is False}
        if not grounded["state_matches"]:
            raise ValueError("Generated image contradicts current object state")
        for obj in grounded["objects"]:
            if obj["id"] in required and not obj["visible"]:
                raise ValueError("Generated image lost an interactive object: " + obj["id"])
            if obj["id"] in hidden and obj["visible"]:
                raise ValueError("Generated image restored a hidden object: " + obj["id"])
        if reference is not None:
            if not grounded.get("layout_preserved"):
                raise ValueError("Video changed the reference scene layout")
            for obj in grounded["objects"]:
                if obj["id"] not in required:
                    continue
                x1, y1, x2, y2 = self.layout.box(obj["box_2d"])
                if min(x2 - x1, y2 - y1) < 8:
                    raise ValueError("Video cropped an interactive object: " + obj["id"])
        movable = {obj["id"] for obj in objects if obj.get("movable")}
        for obj in grounded["objects"]:
            obj["safe_to_move"] = obj["safe_to_move"] and obj["id"] in movable
        folder.mkdir(parents=True, exist_ok=True)
        return self.layout.build(frame, grounded, folder, on_located)

    def _edit(self, reference: Path, prompt: str) -> Image.Image:
        response = requests.post(self.url + "/edit", json={
            "image": base64.b64encode(reference.read_bytes()).decode(), "instruction": prompt,
        }, timeout=(5, 120))
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as decoded:
            edited = decoded.convert("RGB")
        with Image.open(reference) as original:
            if edited.size != original.size:
                raise ValueError("Generated image size differs from the scene")
        return edited
