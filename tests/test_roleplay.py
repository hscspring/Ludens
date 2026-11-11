import json
import shutil
import unittest
import threading
import time
import uuid

import requests
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.tavern.data_model import Action, SceneWorld
from pipeline.tavern.api import Cassian, TavernSession
from pipeline.tavern.video import SceneVideo
from pipeline.tavern.story import SceneStory

ROOT = Path(__file__).resolve().parents[1]


class RoleplayTest(unittest.TestCase):
    def test_object_invitation_is_contextual_and_first_notice_is_not_repeated(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {
            "music": "tense", "title": "雨夜", "motive": "整理旧账", "background": "秘密", "boundary": "不翻账册",
            "objects": [{"id": key, "name": name, "description": name, "background": "未公开的私人往事",
                         "notice": key == "crate", "lead": {"hint": "箱里有旧账册。", "options": [
                             {"label": "问问旧账", "text": "这些账还没结清吗？"}]}}
                        for key, name in [("crate", "木箱"), ("towels", "毛巾"), ("window", "雨窗")]],
            "opportunities": ["谈谈旧账"],
            "object_leads": {"crate": {"hint": "箱里有旧账册。", "options": [
                {"label": "问问旧账", "text": "这些账还没结清吗？"}]}},
        }
        story = SceneStory(llm, ROOT / "pipeline/tavern/cards/rainy_tavern.json")
        config = json.loads((ROOT / "pipeline/tavern/cards/rainy_tavern_assets.json").read_text())
        video = SceneVideo(ROOT / "research/out/roleplay_live_20260925", config["assets"], config["video"])
        session = TavernSession(Cassian(llm), story=story, video=video)
        session.respond_live()
        self.assertEqual(session.snapshot()["music"], "tense")
        self.assertEqual(session.snapshot()["world"]["objects"][0]["lead"]["options"][0]["label"], "问问旧账")
        reply = {"music": "warm", "line": "他抬起手掌。先别翻，好吗？", "expression": "hesitant", "video": False, "duration": 4,
                 "memories": ["先别翻，好吗？", "未公开的私人往事"],
                 "suggestions": [{"label": "尊重边界", "text": "好，你愿意说的时候再说。"}],
                 "moment": {"target": "crate", "title": "他的话停了一下", "image": "A restrained open palm gesture."},
                 "object_leads": {"crate": {"hint": "他刚刚提出了边界。", "options": [
                     {"label": "问问缘由", "text": "是不方便让我知道的事吗？"}]}}}
        llm.call_json.return_value = reply
        session.act(Action(kind="inspect", target="crate"))
        story.jobs.join()
        self.assertEqual(llm.call_json.call_count, 4)
        self.assertNotIn("未公开的私人往事", llm.call_json.call_args.args[1])
        self.assertEqual(session.snapshot()["moment"]["target"], "crate")
        self.assertEqual(session.events[-1]["memories"], ["先别翻，好吗？"])
        self.assertEqual(session.snapshot()["music"], "warm")
        self.assertEqual(session.events[-1]["music"], "warm")
        self.assertEqual(session.snapshot()["world"]["objects"][0]["lead"]["options"][0]["label"], "问问缘由")
        session.act(Action(kind="inspect", target="crate"))
        story.jobs.join()
        self.assertEqual(llm.call_json.call_count, 4)
        llm.call_json.return_value = {**reply, "music": None, "line": "谢谢，我只是还没准备好。", "moment": None, "object_leads": {}}
        session.act(Action(kind="talk", text="好，你愿意说的时候再说。"))
        story.jobs.join()
        self.assertIsNone(session.snapshot()["moment"])
        self.assertEqual(session.snapshot()["music"], "warm")
        self.assertEqual(session.snapshot()["world"]["objects"][0]["lead"]["options"], [])
        self.assertEqual(session.world.positions, {"crate": 0, "towels": 0, "window": 0})
        self.assertNotIn("未公开的私人往事", json.dumps(session.snapshot(), ensure_ascii=False))
        calls = llm.call_json.call_count
        session.act(Action(kind="inspect", target="window"))
        self.assertEqual(llm.call_json.call_count, calls)
        llm.call_json.return_value = {**reply, "moment": None, "reactions": ["window"], "line": "这阵雨让我想起了那次告别。"}
        session.act(Action(kind="talk", text="你为什么一直看着外面的雨？"))
        story.jobs.join()
        window = next(obj for obj in session.snapshot()["world"]["objects"] if obj["id"] == "window")
        self.assertTrue(window["inspected"])
        self.assertTrue(window["inspect_ready"])
        calls = llm.call_json.call_count
        session.act(Action(kind="inspect", target="window"))
        story.jobs.join()
        self.assertEqual(llm.call_json.call_count, calls + 2)
        self.assertIsNone(session.snapshot()["moment"])
        self.assertEqual(session.world.reactions, set())
        session.act(Action(kind="inspect", target="window"))
        story.jobs.join()
        self.assertEqual(llm.call_json.call_count, calls + 2)
        llm.call_json.return_value = {**reply, "reactions": [], "moment": None}
        session.act(Action(kind="talk", text="我们换个话题吧。"))
        story.jobs.join()
        self.assertEqual(session.world.reactions, set())

    def test_canon_is_initialized_once_and_actions_keep_their_consequences(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {
            "title": "雨夜", "motive": "想找人聊聊", "background": "来自海边", "boundary": "不喜欢被催促",
            "objects": [{"id": "crate", "name": "木箱", "description": "里面放着旧账册", "background": "前任店主留下"},
                        {"id": "towels", "name": "毛巾", "description": "浅色条纹毛巾", "background": "留给来客"},
                        {"id": "window", "name": "雨窗", "description": "窗上有雨滴", "background": "他喜欢听雨"}],
            "opportunities": ["聊聊以前的生活"],
        }
        story = SceneStory(llm, ROOT / "pipeline/tavern/cards/rainy_tavern.json")
        setting = story.initialize()
        assets = json.loads((ROOT / "pipeline/tavern/cards/rainy_tavern_assets.json").read_text())["assets"]
        world = SceneWorld(setting, assets)
        second_world = SceneWorld(setting, assets)
        canon = setting.model_dump_json()
        description = world.perform(Action(kind="inspect", target="crate"))
        self.assertNotIn("前任", description)
        self.assertNotIn("前任", json.dumps(world.snapshot(), ensure_ascii=False))
        self.assertEqual(world.perform(Action(kind="inspect", target="window")), "窗上有雨滴")
        self.assertEqual({choice["target"] for choice in world.choices()}, {"crate"})
        with self.assertRaises(ValueError):
            world.perform(Action(kind="move", target="towels", delta=16))
        world.perform(Action(kind="move", target="crate", delta=16))
        with self.assertRaises(ValueError):
            world.perform(Action(kind="move", target="missing", delta=16))
        llm.call_json.return_value = {"line": "以前我常去看海。", "expression": "smiles gently", "attention": "character", "video": False, "duration": 4}
        events = [{"actor": "你", "kind": "say", "text": "说说你以前的生活吧"}]
        story.respond(setting, world.snapshot(), events, [])
        story.respond(setting, world.snapshot(), events, [])
        context = json.loads(llm.call_json.call_args.args[1])
        self.assertEqual(llm.call_json.call_count, 4)
        self.assertEqual(setting.model_dump_json(), canon)
        self.assertEqual(context["canon"]["objects"][0]["background"], "前任店主留下")
        self.assertEqual(context["world"]["objects"][0]["dx"], 16)
        self.assertEqual(second_world.positions["crate"], 0)
        llm.call_json.return_value["video_line"] = "这句不是角色刚才说的话。"
        reply = story.respond(setting, world.snapshot(), events, [])
        self.assertEqual(reply.line, "以前我常去看海。")
        self.assertEqual(reply.video_line, "")
        llm.call_json.return_value["reactions"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "nonexistent object"):
            story.respond(setting, world.snapshot(), events, [])

    def test_object_recollections_only_contain_attributed_spoken_quotes(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {
            "title": "雨夜", "motive": "聊天", "background": "隐藏的身世", "boundary": "不谈往事",
            "objects": [{"id": key, "name": name, "description": name, "background": "尚未公开的秘密"}
                        for key, name in [("crate", "木箱"), ("towels", "毛巾"), ("window", "雨窗")]],
            "opportunities": ["聊聊雨"],
        }
        story = SceneStory(llm, ROOT / "pipeline/tavern/cards/rainy_tavern.json")
        config = json.loads((ROOT / "pipeline/tavern/cards/rainy_tavern_assets.json").read_text())
        video = SceneVideo(ROOT / "research/out/roleplay_live_20260925", config["assets"], config["video"])
        session = TavernSession(Cassian(llm), story=story, video=video)
        session.respond_live()
        state = session.act(Action(kind="inspect", target="towels"))
        self.assertFalse(state["pending"])
        self.assertFalse(state["leads_pending"])
        self.assertEqual(llm.call_json.call_count, 2)
        self.assertEqual(state["object_quotes"], [])
        self.assertNotIn("尚未公开的秘密", json.dumps(state, ensure_ascii=False))
        line = "这些毛巾是留给雨夜来客的。"
        llm.call_json.return_value = {
            "line": line, "expression": "calm", "video": False, "duration": 4,
            "suggestions": [{"label": "好奇地询问", "text": "经常有人来避雨吗？", "intent": "ask"}],
            "object_quotes": [{"target": "towels", "quote": line},
                              {"target": "crate", "quote": "尚未公开的秘密"},
                              {"target": "missing", "quote": line}],
        }
        state = session.act(Action(kind="talk", text="毛巾是为谁准备的？"))
        self.assertTrue(state["leads_pending"])
        story.jobs.join()
        state = session.snapshot()
        self.assertFalse(state["leads_pending"])
        seq = state["events"][-1]["seq"]
        self.assertEqual(state["object_quotes"], [{"target": "towels", "quote": line, "seq": seq, "actor": "Cassian"}])
        self.assertEqual(session.event(seq)["text"], line)
        self.assertEqual(session.event(seq)["video"]["status"], "available")
        self.assertEqual(session.events[0]["video"]["status"], "available")
        self.assertEqual(video.jobs.unfinished_tasks, 0)
        self.assertEqual(state["suggestions"], [{"label": "好奇地询问", "text": "经常有人来避雨吗？", "intent": "ask"}])
        session.act(Action(kind="inspect", target="window"))
        self.assertEqual(session.snapshot()["suggestions"], state["suggestions"])
        replay = session.start_replay()["replay"]
        llm.call_json.return_value = {"line": "我也喜欢听雨。", "expression": "calm", "video": False, "duration": 4}
        session.act(Action(kind="move", target="crate", delta=16))
        story.jobs.join()
        session.act(Action(kind="inspect", target="towels"))
        self.assertEqual(session.snapshot()["suggestions"], [])
        self.assertEqual(session.snapshot()["object_quotes"], state["object_quotes"])
        self.assertEqual(session.snapshot()["replay"], replay)
        self.assertTrue(session.event_image(session.events[-1]["seq"]).is_file())
        self.assertEqual(session.world.positions, {"crate": 16, "towels": 0, "window": 0})
        self.assertNotIn("尚未公开的秘密", json.dumps(session.snapshot(), ensure_ascii=False))

    def test_optional_video_and_replay_never_block_or_rewrite_the_world(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {
            "title": "雨夜的旧账", "motive": "整理账册", "background": "前任店主照顾过他", "boundary": "不随便公开旧账",
            "objects": [{"id": "crate", "name": "木箱", "description": "装着旧账册", "background": "尚未公开的秘密"},
                        {"id": "towels", "name": "毛巾", "description": "浅色条纹毛巾", "background": "留给来客"},
                        {"id": "window", "name": "雨窗", "description": "窗上有雨滴", "background": "他喜欢听雨"}],
            "opportunities": ["聊聊旧账"],
        }
        story = SceneStory(llm, ROOT / "pipeline/tavern/cards/rainy_tavern.json")
        config = json.loads((ROOT / "pipeline/tavern/cards/rainy_tavern_assets.json").read_text())
        folder = ROOT / "research/out/v01_validation" / uuid.uuid4().hex
        initial = folder / "media/initial"
        initial.mkdir(parents=True)
        for key in ("frame", "background"):
            destination = initial / f"{key}.webp"
            shutil.copyfile(config["assets"]["initial"][key], destination)
            config["assets"]["initial"][key] = str(destination)
        sprite = initial / "crate.webp"
        shutil.copyfile(config["assets"]["initial"]["objects"]["crate"]["sprite"], sprite)
        config["assets"]["initial"]["objects"]["crate"]["sprite"] = str(sprite)
        video = SceneVideo(folder, config["assets"], config["video"])
        session = TavernSession(Cassian(llm), story=story, video=video)
        session.respond_live()
        llm.call_json.return_value = {
            "line": "先放那儿吧。" + "这些账册让我想起以前的日子，我也想听听你的看法。" * 3,
            "video_line": "先放那儿吧。", "expression": "a brief reflective glance", "video": True,
            "duration": 4, "attention": None,
        }
        entered, release = threading.Event(), threading.Event()

        def infer(*args: object, **kwargs: object) -> requests.Response:
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Inference test was not released")
            raise requests.ConnectionError("Video backend unavailable")

        with patch("pipeline.tavern.video.requests.post", side_effect=infer) as inference:
            session.act(Action(kind="talk", text="你为什么还没整理这些账？"))
            deadline = time.monotonic() + 3
            while session.snapshot()["pending"] and time.monotonic() < deadline:
                time.sleep(0.01)
            state = session.snapshot()
            self.assertIsNone(state["npc_error"])
            self.assertGreater(len(state["events"][-1]["text"]), 50)
            inference.assert_not_called()
            seq = state["events"][-1]["seq"]
            replay = session.start_replay()["replay"]
            self.assertEqual(len(replay["events"]), 3)
            self.assertNotIn("尚未公开的秘密", json.dumps(replay, ensure_ascii=False))
            session.request_video(seq)
            self.assertTrue(entered.wait(2))
            session.request_video(seq)
            session.act(Action(kind="move", target="crate", delta=16))
            deadline = time.monotonic() + 3
            while session.snapshot()["pending"] and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(session.snapshot()["pending"])
            self.assertEqual(session.world.positions["crate"], 16)
            self.assertEqual(session.event(seq)["world"]["objects"][0]["dx"], 0)
            self.assertEqual(len(session.snapshot()["replay"]["events"]), 3)
            release.set()
            deadline = time.monotonic() + 3
            while session.event(seq)["video"]["status"] != "failed" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(session.event(seq)["video"]["status"], "failed")
            self.assertEqual(session.world.positions["crate"], 16)
            self.assertIsNone(session.snapshot()["npc_error"])
            self.assertEqual(inference.call_count, 1)
            self.assertTrue(session.event_image(seq).is_file())
            self.assertEqual(session.start_replay()["replay"]["events"], session.snapshot()["events"])
        response = requests.Response()
        response.status_code = 200
        response._content = (ROOT / "pipeline/tavern/static/video-quality-20260922/liveavatar_character.mp4").read_bytes()
        seq = session.events[-1]["seq"]
        with patch("pipeline.tavern.video.requests.post", return_value=response):
            session.request_video(seq)
            deadline = time.monotonic() + 15
            while session.event(seq)["video"]["status"] in {"queued", "generating"} and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(session.event(seq)["video"]["status"], "ready")
            self.assertEqual(session.world.positions["crate"], 16)
            self.assertEqual(session.snapshot()["replay"]["events"][-1]["video"]["status"], "available")



if __name__ == "__main__":
    unittest.main()
