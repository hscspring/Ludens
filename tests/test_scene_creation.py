import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.tavern.creation import SceneCreator
from pipeline.tavern.data_model import SceneCreate


class SceneCreationTest(unittest.TestCase):
    def test_rejected_plan_never_becomes_a_playable_story(self) -> None:
        service = Mock()
        plan = {'supported':True, 'title':'车内', 'character':'Hozumi', 'player_role':'歌手',
                'entry':'车内', 'prologue':'已经上车', 'opening_line':'你怎么想？',
                'image_prompt':'One woman in a car',
                'objects':[{'id':'window','name':'窗户','description':'玻璃窗'}]}
        folder = Path('/mnt/sv0/sean/Ludens/research/out/scene_creation_20261009') / uuid.uuid4().hex
        with patch('pipeline.tavern.creation.LLMClient') as client, patch('pipeline.tavern.creation.requests.post') as network:
            client.return_value.call_json.side_effect = [plan, {'valid':False,'issues':['changed player identity']}]
            creator = SceneCreator(service, folder, 'http://image.test')
            job = creator.submit(SceneCreate(personality='保镖', welcomeMessage='你在车里。'))
            creator.jobs.join()
            self.assertEqual(creator.status(job['id'])['status'], 'failed')
            service.register.assert_not_called()
            network.assert_not_called()
            self.assertEqual(creator.layout.box([250,250,750,750]), [168,96,504,288])
            with self.assertRaises(ValueError):
                creator.layout.box([0,0,1001,1000])
