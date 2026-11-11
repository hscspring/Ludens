import copy
import json
import unittest
from unittest.mock import Mock, patch

import requests

from llm_client import LLMClient
from pipeline.tavern.interaction import InteractionModel


class InteractionFallbackTest(unittest.TestCase):
    def test_validate_before_return_and_fallback_on_failed_local_output(self) -> None:
        endpoint = {"name": "fallback", "base_url": "http://fallback/v1", "model": "fallback",
                    "key_env": "LUDENS_TEST_UNUSED_KEY", "params": {}}
        model = InteractionModel(LLMClient([endpoint], env_file=""), "http://local/v1")
        context = {"world": {"objects": [{"id": "cup", "location": "table"}], "appearance": "seated"}}
        before = copy.deepcopy(context)
        good = {"line": "给你。", "expression": "Smiling.", "duration": 4, "video_line": "给你。",
                "suggestions": [{"label": "谢谢", "text": "谢谢你。"}, {"label": "询问", "text": "里面是什么？"}]}
        invalid = [requests.Timeout("local timeout"), "not JSON", {**good, "video_line": "长" * 31},
                   {**good, "memories": ["没有说过的话"]}, {**good, "reactions": ["missing"]}]
        for candidate in [good, *invalid]:
            raw = json.dumps(candidate, ensure_ascii=False) if isinstance(candidate, dict) else candidate
            local = raw if isinstance(raw, Exception) else Mock(json=lambda: {"choices": [{"message": {"content": raw}}]})
            remote = Mock(json=lambda: {"choices": [{"message": {"content": json.dumps(good)}}]})
            with self.subTest(candidate=candidate), patch("llm_client.requests.post", side_effect=[local, remote]) as post:
                result = model("respond", "system", json.dumps(context), temperature=0.7)
                self.assertEqual(result, good)
                self.assertEqual(context, before)
                self.assertEqual(post.call_count, 1 if candidate == good else 2)
                self.assertEqual(post.call_args_list[0].kwargs["json"]["temperature"], 0)
                if candidate != good:
                    self.assertEqual(post.call_args.args[0], "http://fallback/v1/chat/completions")
        with patch("llm_client.requests.post", side_effect=[
            Mock(json=lambda: {"choices": [{"message": {"content": "bad JSON"}}]}),
            Mock(json=lambda: {"choices": [{"message": {"content": json.dumps(good)}}]}),
        ]) as post:
            client = LLMClient([endpoint, endpoint], env_file="")
            self.assertEqual(client.call_json("system", "user"), good)
            self.assertEqual(post.call_count, 2)
