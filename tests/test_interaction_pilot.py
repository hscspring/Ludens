import copy
import json
import random
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.synthesize_interactions import InteractionPilot


class InteractionPilotTest(unittest.TestCase):
    def test_single_call_replays_random_choices_without_future_leakage(self) -> None:
        options = [{'label': '挪杯子', 'text': '请把杯子挪到桌边。', 'intent': 'ask'},
                   {'label': '商量挪动', 'text': '能把杯子挪到桌边吗？', 'intent': 'ask'}]
        lead = {'hint': '白色杯子', 'options': options}
        plan = {'supported': True, 'title': '休息室', 'character': 'Lin', 'player_role': '同事',
                'entry': '午休', 'prologue': '你走进休息室。', 'opening_line': '午休了。',
                'image_prompt': 'One adult in a break room.',
                'objects': [{'id': 'cup', 'name': '杯子', 'description': '白色杯子'}]}
        setting = {'title': '休息室', 'character': 'Lin', 'motive': '休息', 'background': '同事', 'boundary': '尊重休息',
                   'objects': [{'id': 'cup', 'name': '杯子', 'description': '白色杯子', 'lead': lead,
                                'background': '平时喝水', 'visual': 'A white cup on the table.', 'notice': False}],
                   'opportunities': ['一起休息'], 'suggestions': options}
        reply = {'line': '先一起休息吧。', 'video_line': '先一起休息吧。', 'expression': 'A small smile.',
                 'duration': 4, 'suggestions': options}
        moved = {**reply, 'line': '好，我把杯子放到桌边了。', 'video_line': '好，我把杯子放到桌边了。',
                 'object_updates': [{'id': 'cup', 'description': '白色杯子', 'location': '桌边',
                                     'visible': True, 'visual': 'The same white cup at the table edge.'}]}
        identifier = '0000000000000001'
        rng = random.Random(int(identifier, 16))
        choices = [rng.randrange(2) for _ in range(rng.choice((3, 4)))]
        bundle = {'accepted': True, 'reason': '', 'plan': plan, 'setting': setting,
                  'turns': [{'reply': copy.deepcopy(moved if i == 0 else reply),
                             'object_leads': [{'id': 'cup', **lead}]} for i in range(len(choices))]}
        network = Mock(json=Mock(return_value={'choices': [{'message': {'content': json.dumps(bundle)}}]}))
        output = Path('/mnt/sv0/sean/Ludens/research/out/interaction_tests') / uuid.uuid4().hex
        output.mkdir(parents=True)
        selected = {'id': identifier, 'source': {'personality': 'Lin 是成年同事。',
                    'scenario': '你和 Lin 在休息室。', 'welcomeMessage': '午休了。'}}
        with patch('llm_client.requests.post', return_value=network) as request:
            result = InteractionPilot(output, 1, 1).generate(selected)
        self.assertEqual(request.call_count, 1)
        self.assertTrue(result['accepted'], result['reason'])
        self.assertEqual(result['choices'], choices)
        self.assertEqual(len(result['samples']), 2 * len(choices))
        self.assertEqual(result['turns'][0]['after']['objects'][0]['lead']['options'], options)
        self.assertEqual(result['turns'][1]['before']['objects'][0]['location'], '桌边')
        first = json.loads(result['samples'][0]['messages'][1]['content'])
        second = json.loads(result['samples'][2]['messages'][1]['content'])
        self.assertEqual(first['world']['objects'][0]['location'], '开场画面中的位置')
        self.assertEqual(second['world']['objects'][0]['location'], '桌边')
        self.assertNotIn('turns', first)
        self.assertNotIn('choice_indices', first)
        self.assertEqual(first['events'][-1]['text'], options[choices[0]]['text'])
        self.assertNotIn('Authorization', json.dumps(result['calls']))
