import json
import threading
import time
import unittest
from unittest.mock import Mock

from pipeline.tavern.api import Cassian, TavernSession
from pipeline.tavern.data_model import Action, CrateWorld, TavernWorld


class TavernTest(unittest.TestCase):
    def test_minimax_crate_stays_on_table_and_character_only_talks(self) -> None:
        llm = Mock()
        llm.call_json.return_value = {"line": "放在那儿就好。", "action": None}
        world = CrateWorld(min_dx=0, max_dx=128, slope=0.45, npc_actions=False)
        session = TavernSession(Cassian(llm), world)
        with self.assertRaises(ValueError):
            session.act(Action(kind="crate_left"))
        for _ in range(4):
            world.perform(Action(kind="crate_right"))
        self.assertEqual(world.snapshot()["crate_dy"], 58)
        with self.assertRaises(ValueError):
            world.perform(Action(kind="crate_right"))
        session.act(Action(kind="talk", text="我刚把箱子挪到哪儿了？"))
        deadline = time.monotonic() + 3
        while session.snapshot()["pending"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(session.snapshot()["pending"])
        scene = json.loads(llm.call_json.call_args.args[1])
        self.assertEqual(scene["world"]["crate_dx"], 128)
        self.assertEqual(scene["choices"], [])
        self.assertEqual(session.snapshot()["events"][-1]["text"], "放在那儿就好。")

    def test_crate_remembers_moves_while_speech_is_pending(self) -> None:
        llm = Mock()
        entered, release = threading.Event(), threading.Event()

        def respond(system: str, user: str, **kwargs) -> dict:
            entered.set()
            if not release.wait(3):
                raise TimeoutError("Test did not release LLM")
            return {"line": "就放在左边吧。", "action": None}

        llm.call_json.side_effect = respond
        speech = Mock()
        session = TavernSession(Cassian(llm), CrateWorld(), speech)
        welcome_done = speech.submit.call_args.args[2]
        state = session.act(Action(kind="crate_left"))
        self.assertEqual(state["world"]["crate_dx"], -32)
        self.assertEqual(state["world"]["ledger"], "inside_crate")
        self.assertTrue(entered.wait(1))
        welcome_done({"status": "ready", "path": "/unused.wav"})
        release.set()
        deadline = time.monotonic() + 3
        while session.snapshot()["pending"] and time.monotonic() < deadline:
            time.sleep(0.01)
        state = session.snapshot()
        self.assertFalse(state["pending"])
        self.assertIsNone(state["npc_error"])
        self.assertEqual(llm.call_json.call_count, 1)
        self.assertEqual(state["events"][-1]["speech"]["status"], "queued")
        session.act(Action(kind="crate_right"))
        self.assertEqual(session.snapshot()["world"]["crate_dx"], 0)
        world = CrateWorld(-96)
        with self.assertRaises(ValueError):
            world.perform(Action(kind="crate_left"))
        self.assertEqual(world.crate_dx, -96)

    def test_objects_keep_their_consequences(self) -> None:
        world = TavernWorld()
        world.perform(Action(kind="ledger_safe"))
        world.perform(Action(kind="crate_safe"))
        world.perform(Action(kind="crate_wet"))
        self.assertTrue(world.records_safe)
        self.assertEqual(world.ledger, "shelf")
        world.perform(Action(kind="bucket_catch"))
        world.perform(Action(kind="wipe", target="towel_1"))
        self.assertTrue(world.snapshot()["settled"])
        self.assertTrue(world.snapshot()["leak_active"])
        self.assertEqual(world.towels, {"towel_1": "wet", "towel_2": "dry"})
        before = world.snapshot()
        with self.assertRaises(ValueError):
            world.perform(Action(kind="wipe", target="towel_1"))
        self.assertEqual(world.snapshot(), before)
        world.perform(Action(kind="wring", target="towel_1"))
        self.assertEqual(world.towels["towel_1"], "damp")
        world.perform(Action(kind="bucket_floor"))
        self.assertTrue(world.puddle)
        self.assertFalse(world.snapshot()["settled"])

    def test_slow_character_does_not_block_or_overwrite_new_actions(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        latest = []

        def respond(system: str, user: str, **kwargs) -> dict:
            scene = json.loads(user)
            latest.append(scene)
            if len(latest) == 1:
                entered.set()
                if not release.wait(3):
                    raise TimeoutError("Test did not release LLM")
                return {"line": "旧的回应，不应该出现。", "action": {"kind": "crate_safe"}}
            return {"line": "账册放在那里就好，我来擦水。", "action": {"kind": "wipe", "target": "towel_1"}}

        llm = Mock()
        llm.call_json.side_effect = respond
        session = TavernSession(Cassian(llm))
        other = TavernSession(Cassian(llm))
        session.act(Action(kind="bucket_catch"))
        self.assertTrue(entered.wait(1))
        start = time.monotonic()
        state = session.act(Action(kind="ledger_safe"))
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertTrue(state["pending"])
        self.assertEqual(state["world"]["ledger"], "shelf")
        release.set()
        deadline = time.monotonic() + 3
        while session.snapshot()["pending"] and time.monotonic() < deadline:
            time.sleep(0.01)
        state = session.snapshot()
        self.assertFalse(state["pending"])
        self.assertIsNone(state["npc_error"])
        self.assertEqual(len(latest), 2)
        self.assertEqual(state["world"]["crate"], "wet")
        self.assertEqual(state["world"]["ledger"], "shelf")
        self.assertFalse(state["world"]["puddle"])
        self.assertNotIn("旧的回应", json.dumps(state, ensure_ascii=False))
        self.assertEqual(other.world.bucket, "floor")
        self.assertEqual(other.world.ledger, "crate")


if __name__ == "__main__":
    unittest.main()
