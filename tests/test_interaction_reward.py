import copy
import json
import unittest
from unittest.mock import Mock

from pipeline.tavern.reward import InteractionReward


class InteractionRewardTest(unittest.TestCase):
    def test_current_turn_state_and_invalid_outputs(self) -> None:
        reward = InteractionReward()
        reward.judge = Mock()
        reward.judge.call_json.return_value = dict(critical_error=False, relevance=1.0, consistency=1.0, presentation=1.0,
                                                   play=1.0, reason='consistent')
        context = {'world': {'objects': [{'id': 'cup', 'location': 'table'}], 'appearance': 'seated'},
                   'events': [{'actor': '你', 'text': '请把杯子递给我。'}]}
        messages = [{'role': 'system', 'content': 'Generate the current reply.'},
                    {'role': 'user', 'content': json.dumps(context)}]
        options = [{'label': '谢谢', 'text': '谢谢你。'}, {'label': '询问', 'text': '里面是什么？'}]
        candidate = {'line': '给你。', 'expression': 'Smiling.', 'duration': 4, 'suggestions': options,
                     'video_line': '给你。', 'object_updates': [{'id': 'cup', 'description': '白杯子',
                       'location': '玩家手中', 'visible': True, 'visual': 'A white cup in player hands.'}]}
        valid = reward('respond', messages, json.dumps(candidate))
        self.assertEqual(valid['score'], 1)
        payload = json.loads(reward.judge.call_json.call_args.args[1])
        self.assertEqual(payload['computed_after']['objects'][0]['location'], '玩家手中')
        self.assertEqual(payload['messages'], messages)
        self.assertEqual(context['world']['objects'][0]['location'], 'table')
        for key, value in [('video_line', '我没说过这句。'), ('reactions', ['unknown'])]:
            broken = {**candidate, key: value}
            self.assertEqual(reward('respond', messages, json.dumps(broken))['score'], -1)
        invalid = reward('respond', messages, 'not JSON')
        self.assertEqual(invalid['score'], -1)
        self.assertEqual(set(valid), set(invalid))
        self.assertIs(invalid['critical_error'], True)
        self.assertEqual(reward.judge.call_json.call_count, 1)
        leads_input = copy.deepcopy(messages)
        leads_input[-1]['content'] = json.dumps({'objects': [{'id': 'cup'}]})
        leads = {'object_leads': {'cup': {'hint': '手中的杯子', 'options': options}}}
        self.assertEqual(reward('public_leads', leads_input, json.dumps(leads))['score'], 1)
        self.assertEqual(reward('public_leads', leads_input, '{"object_leads": {}}')['score'], -1)
        reward.judge.call_json.return_value['consistency'] = 0.0
        self.assertEqual(reward('respond', messages, json.dumps(candidate))['score'], 0)
        reward.judge.call_json.return_value.update(consistency=0.5, critical_error=True)
        self.assertEqual(reward('respond', messages, json.dumps(candidate))['score'], 0)
