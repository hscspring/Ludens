import copy
import base64
import io
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image, ImageChops

from pipeline.tavern.api import Cassian, TavernSession
from pipeline.tavern.data_model import Action, Playback
from pipeline.tavern.image import SceneImage
from pipeline.tavern.story import SceneStory
from pipeline.tavern.video import SceneVideo

ROOT = Path(__file__).resolve().parents[1]


class RoleplayImagesTest(unittest.TestCase):
    def test_async_images_preserve_world_history_and_replay(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {
            "title": "雨夜", "motive": "整理账册", "background": "前任店主的旧账", "boundary": "保留隐私",
            "objects": [{"id": "crate", "name": "木箱", "description": "旧账册", "background": "旧友的往事"},
                        {"id": "towels", "name": "毛巾", "description": "浅色条纹毛巾", "background": "留给来客"},
                        {"id": "window", "name": "雨窗", "description": "窗上有雨滴", "background": "他喜欢听雨"}],
            "opportunities": ["聊天"],
        }
        config = json.loads((ROOT / "pipeline/tavern/cards/rainy_tavern_assets.json").read_text())
        video = SceneVideo(ROOT / "research/out/roleplay_live_20260925", config["assets"], config["video"])
        images = SceneImage("http://image-test.invalid")
        images.layout.llm.call_json = Mock(return_value={
            "state_matches": True, "character_matches": True, "visible_people_count": 1, "scene_matches": True,
            "objects_belong_to_same_character": True,
            "character": {"visible": True, "box_2d": [0, 100, 950, 550], "face_box_2d": [20, 130, 300, 400]},
            "objects": [{"id": key, "visible": True, "box_2d": [500, 600, 700, 800],
                         "description": "新画面中的物品", "safe_to_move": key == "towels",
                         "movement": {"min_dx": -16, "max_dx": 0, "slope": 0}}
                        for key in ("crate", "towels", "window")],
        })
        story = SceneStory(llm, ROOT / "pipeline/tavern/cards/rainy_tavern.json")
        story.card["object_contents"] = {"towels": "记录时间17:08；设备时钟快12分钟。"}
        session = TavernSession(Cassian(llm), story=story, video=video, image=images)
        session.respond_live()
        self.assertEqual(session.snapshot()["world"]["objects"][1]["contents"], "")
        inspected = session.act(Action(kind="inspect", target="towels"))
        self.assertIn("17:08", inspected["events"][-1]["text"])
        self.assertEqual(inspected["world"]["objects"][1]["contents"], story.card["object_contents"]["towels"])
        def locate(*args: object, **kwargs: object) -> dict:
            state = session.snapshot()
            event = session.event(session.latest_reply)
            if event.get("image", {}).get("status") == "locating" and session._current_scene(session.latest_reply):
                self.assertEqual(state["preview"], event["image"]["url"])
                self.assertNotEqual(session.visual["frame"], event["image"]["path"])
                with self.assertRaisesRegex(ValueError, "物品位置正在确认"):
                    session.act(Action(kind="move", target="crate", delta=16))
            return images.layout.llm.call_json.return_value
        images.layout.llm.call_json.side_effect = locate
        original = copy.deepcopy(session.visual)
        first_frame = session.event_image(session.events[0]["seq"]).read_bytes()
        entered, release = threading.Event(), threading.Event()
        response = requests.Response()
        response.status_code = 200
        output = io.BytesIO()
        Image.new("RGB", (672, 384), (240, 80, 20)).save(output, format="PNG")
        response._content = output.getvalue()

        def infer(url: str, **kwargs: object) -> requests.Response:
            if url.endswith("/v1/videos/sync"):
                raise requests.ConnectionError("Video intentionally unavailable")
            self.assertEqual(base64.b64decode(kwargs["json"]["image"]), Path(video.assets["initial"]["frame"]).read_bytes())
            entered.set()
            if not release.wait(5):
                raise requests.Timeout("Test did not release image inference")
            return response

        reply = {"line": "你这么说，让我想起以前。", "video_line": "你这么说，让我想起以前。",
                 "expression": "soft smile", "video": True, "duration": 4, "image": "soft smile"}
        llm.call_json.return_value = reply
        with patch("pipeline.tavern.image.requests.post", side_effect=infer):
            session.act(Action(kind="talk", text="不用急，慢慢说。"))
            story.jobs.join()
            self.assertTrue(entered.wait(2))
            older = session.events[-1]["seq"]
            replay = session.start_replay()["replay"]
            self.assertFalse(session.snapshot()["pending"])
            self.assertEqual(session.event(older)["image"]["status"], "generating")
            session.request_video(older)
            video.jobs.join()
            frozen_reference = session.event(older)["video"]["reference"]
            llm.call_json.return_value = {**reply, "image": None, "video": False}
            session.act(Action(kind="move", target="crate", delta=16))
            story.jobs.join()
            newer = session.events[-1]["seq"]
            release.set()
            images.jobs.join()
            self.assertEqual(session.visual, original)
            self.assertEqual(session.world.positions["crate"], 16)
            self.assertEqual(session.event(older)["image"]["status"], "ready")
            self.assertIsNone(session.snapshot()["preview"])
            self.assertEqual(session.snapshot()["replay"], replay)
            self.assertEqual(session.event_image(session.events[0]["seq"]).read_bytes(), first_frame)
            self.assertNotEqual(str(session.event_image(older)), frozen_reference)
            self.assertEqual(session.event(newer)["visual"], original)
            llm.call_json.return_value = reply
            session.act(Action(kind="talk", text="你愿意再多讲一点吗？"))
            story.jobs.join()
            images.jobs.join()
            latest = session.events[-1]["seq"]
            self.assertNotEqual(session.visual["frame"], original["frame"])
            self.assertEqual(session.world.positions["crate"], 0)
            self.assertFalse(session.world.movable["crate"])
            self.assertEqual(session.snapshot()["world"]["objects"][1]["contents"], story.card["object_contents"]["towels"])
            self.assertNotEqual(session.assets["character_region"], config["assets"]["character_region"])
            self.assertTrue(next(obj for obj in session.world.snapshot()["objects"] if obj["id"] == "window")["position_verified"])
            with Image.open(original["frame"]) as before, Image.open(session.visual["frame"]) as after:
                bounds = ImageChops.difference(before, after).getbbox()
            self.assertIsNotNone(bounds)
            self.assertEqual(bounds, (0, 0, 672, 384))
            self.assertNotEqual(session.event_image(latest).read_bytes(), session.event_image(latest, rendered=False).read_bytes())
        committed = copy.deepcopy(session.visual)
        grounded_object = images.layout.llm.call_json.return_value["objects"][0]
        grounded_object["visible"] = False
        with patch("pipeline.tavern.image.requests.post", return_value=response):
            session.act(Action(kind="talk", text="我还在听。"))
            story.jobs.join()
            images.jobs.join()
        self.assertEqual(session.events[-1]["image"]["status"], "failed")
        self.assertEqual(session.visual, committed)
        grounded_object["visible"] = True
        with patch("pipeline.tavern.image.requests.post", side_effect=requests.ConnectionError("Offline")):
            session.act(Action(kind="talk", text="没事，明天再说。"))
            story.jobs.join()
            images.jobs.join()
        self.assertEqual(session.events[-1]["image"]["status"], "failed")
        self.assertIsNone(session.snapshot()["preview"])
        self.assertEqual(session.visual, committed)
        self.assertFalse(session.pending)
        self.assertIsNone(session.npc_error)
        moment_reply = {**reply, "image": None, "video": False,
                        "moment": {"target": "crate", "title": "先等一下", "image": "An open palm near the crate."}}
        llm.call_json.return_value = moment_reply
        output = io.BytesIO()
        Image.new("RGB", (672, 384), (20, 80, 240)).save(output, format="PNG")
        response._content = output.getvalue()
        with patch("pipeline.tavern.image.requests.post", return_value=response):
            session.act(Action(kind="talk", text="你不想谈这件事吗？"))
            story.jobs.join()
            images.jobs.join()
        moment = session.snapshot()["moment"]
        self.assertEqual(moment["status"], "ready")
        self.assertNotEqual(session.visual["frame"], committed["frame"])
        self.assertEqual(session.visual["objects"], committed["objects"])
        with Image.open(committed["frame"]) as before, Image.open(session.visual["frame"]) as after:
            bounds = ImageChops.difference(before, after).getbbox()
            self.assertEqual(bounds, (0, 0, 672, 384))
            self.assertEqual(after.getpixel((0, 0)), (20, 80, 240))
        committed = copy.deepcopy(session.visual)
        llm.call_json.return_value = {**reply, "image": None, "video": False}
        session.act(Action(kind="talk", text="好，我明白了。"))
        story.jobs.join()
        self.assertIsNone(session.snapshot()["moment"])
        self.assertEqual(session.visual, committed)
        self.assertEqual(session.world.positions["crate"], 0)
        with Image.open(session.event_image(moment["seq"])) as picture:
            self.assertEqual(picture.getpixel((0, 0)), (20, 80, 240))
        llm.call_json.return_value = moment_reply
        entered.clear()
        release.clear()
        with patch("pipeline.tavern.image.requests.post", side_effect=infer):
            session.act(Action(kind="talk", text="我可以等等。"))
            story.jobs.join()
            self.assertTrue(entered.wait(2))
            old_moment = session.snapshot()["moment"]["seq"]
            llm.call_json.return_value = {**reply, "image": None, "video": False}
            session.act(Action(kind="talk", text="那先聊点别的吧。"))
            story.jobs.join()
            release.set()
            images.jobs.join()
        self.assertIsNone(session.snapshot()["moment"])
        self.assertEqual(session.event(old_moment)["image"]["status"], "ready")
        self.assertEqual(session.visual, committed)
        latest = session.latest_reply
        frame = session.event_image(latest).parent / "last_frame.png"
        Image.new("RGB", (640, 366), (30, 190, 90)).save(frame)
        assets = images.prepare(frame, session.world.snapshot()["objects"], "tavern", frame.parent / "settled")
        session.event(latest)["video"] = {"status": "ready", "scene": assets}
        session.playback(Playback(turn=old_moment, phase="end"))
        self.assertEqual(session.visual, committed)
        session.playback(Playback(turn=latest, phase="start"))
        self.assertEqual(session.visual, committed)
        session.playback(Playback(turn=latest, phase="end"))
        self.assertTrue(session.event(latest)["video"]["applied"])
        with Image.open(committed["frame"]) as before, Image.open(session.visual["frame"]) as after:
            bounds = ImageChops.difference(before, after).getbbox()
            self.assertEqual(bounds, (0, 0, 672, 384))
        self.assertEqual(session.world.positions["crate"], 0)
        settled = copy.deepcopy(session.visual)
        session.playback(Playback(turn=latest, phase="end"))
        self.assertEqual(session.visual, settled)
        result = {"video": str(frame.parent / "play.mp4"), "last_frame": str(frame), "duration": 5, "seconds": 1}
        for outcome in ("repaired", "failed", "stale"):
            committed = copy.deepcopy(session.visual)
            clip = {"status": "queued", "reference": committed["frame"], "line": "好。",
                    "expression": "Attentive gaze", "duration": 5}
            session.event(latest)["video"] = clip
            calls = 0

            def verify(*args: object, **kwargs: object) -> dict:
                nonlocal calls
                calls += 1
                self.assertEqual(clip["status"], "ready")
                if calls == 1:
                    session.playback(Playback(turn=latest, phase="end"))
                    self.assertTrue(clip["playback_ended"])
                    self.assertEqual(session.visual, committed)
                else:
                    self.assertEqual(clip["scene_status"], "repairing")
                    if outcome == "stale":
                        session.pending = True
                return {**images.layout.llm.call_json.return_value,
                        "layout_preserved": calls > 1 and outcome != "failed"}

            images.layout.llm.call_json.side_effect = verify
            with patch.object(video, "generate", return_value=result), patch("pipeline.tavern.image.requests.post", return_value=response):
                session.render_video(latest)
            self.assertEqual(calls, 2)
            self.assertEqual(clip["status"], "ready")
            if outcome == "repaired":
                self.assertTrue(clip["applied"])
                self.assertEqual(clip["scene_status"], "repaired")
                self.assertNotEqual(session.visual, committed)
            else:
                self.assertFalse(clip.get("applied", False))
                self.assertEqual(session.visual, committed)
            self.assertEqual(session.snapshot()["world"]["objects"][1]["contents"], story.card["object_contents"]["towels"])
            session.pending = False

        images.layout.llm.call_json.side_effect = None
        update = {"id": "crate", "description": "装着旧账的木箱", "location": "收在柜中，画面外", "visible": False, "visual": "The crate is stored out of view."}
        llm.call_json.return_value = {**reply, "object_updates": [update], "image": None}
        grounded_object["visible"] = False
        with patch("pipeline.tavern.image.requests.post", return_value=response) as render:
            session.act(Action(kind="talk", text="可以把箱子先收好吗？"))
            story.jobs.join()
            images.jobs.join()
            payload = render.call_args.kwargs["json"]
        self.assertEqual(base64.b64decode(payload["image"]), Path(video.assets["initial"]["frame"]).read_bytes())
        self.assertIn("The crate is stored out of view.", payload["instruction"])
        hidden = session.world.snapshot()["objects"][0]
        self.assertFalse(hidden["visible"])
        self.assertFalse(hidden["position_verified"])
        self.assertEqual(session.events[-1]["object_updates"], [update])
        self.assertIn("收在柜中", session.world.perform(Action(kind="inspect", target="crate")))
        self.assertEqual(session.world.setting.objects[0].description, "旧账册")

        llm.call_json.return_value = {**reply, "line": "暂时先不要取出来。", "image": None}
        session.act(Action(kind="talk", text="现在要拿出来吗？"))
        story.jobs.join()
        self.assertEqual(session.world.object_states["crate"].model_dump(), update)
        committed = copy.deepcopy(session.visual)
        grounded_object["visible"] = True
        llm.call_json.return_value = reply
        with patch("pipeline.tavern.image.requests.post", return_value=response):
            session.act(Action(kind="talk", text="好，那再聊会儿。"))
            story.jobs.join()
            images.jobs.join()
        self.assertEqual(session.events[-1]["image"]["status"], "failed")
        self.assertEqual(session.visual, committed)
        self.assertFalse(session.world.object_states["crate"].visible)

        llm.call_json.return_value = {**reply, "object_updates": [{**update, "location": "重新放到桌面上", "visible": True, "visual": "The crate is back on the table."}]}
        with patch("pipeline.tavern.image.requests.post", return_value=response):
            session.act(Action(kind="talk", text="那把箱子拿回来吧。"))
            story.jobs.join()
            images.jobs.join()
        self.assertTrue(session.world.snapshot()["objects"][0]["position_verified"])
        self.assertEqual(len(session.world.snapshot()["objects"]), 3)


if __name__ == "__main__":
    unittest.main()
