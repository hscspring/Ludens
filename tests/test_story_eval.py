import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import av
from PIL import Image

from research.story_eval import StoryEvaluation


class StoryEvaluationTest(unittest.TestCase):
    def test_reuses_model_and_actual_last_frame_with_one_load_charge(self) -> None:
        self._evaluate(independent=False)

    def test_independent_trials_reset_reference_and_pass_seed_and_end_frame(self) -> None:
        self._evaluate(independent=True)

    def _evaluate(self, independent: bool) -> None:
        out = Path('/mnt/sv0/sean/Ludens/research/out/acceleration_20260924/tests') / uuid4().hex
        out.mkdir(parents=True)
        reference = out / 'initial.png'
        Image.new('RGB', (64, 64), 'blue').save(reference)
        story = dict(title='test', node='24.144.74.183', gpu=3, seed=7,
                     target_width=64, target_height=64, initial_reference=str(reference),
                     models=['joy_fp8'], acceleration_profile='joy_fp8',
                     scenes=[dict(id=str(i), prompt=f'line {i}') for i in range(3)])
        path = out / 'story.json'
        if independent:
            for i, scene in enumerate(story['scenes']):
                scene.update(reference=str(reference), seed=7 + i)
            story['scenes'][-1]['last_image'] = str(reference)
        path.write_text(json.dumps(story))
        seen = []
        conditions = []

        def generate(actual: Path, prompt: str, target: Path, last_image: Path | None = None) -> dict:
            seen.append(actual.read_bytes())
            conditions.append((inference.seed, last_image))
            frame = av.VideoFrame.from_image(Image.new('RGB', (64, 64), (len(seen) * 60, 20, 10)))
            with av.open(str(target / 'joy_fp8_character.mp4'), 'w') as container:
                stream = container.add_stream('libx264', rate=24)
                stream.width = stream.height = 64
                stream.pix_fmt = 'yuv420p'
                for packet in stream.encode(frame):
                    container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            metrics = dict(response_seconds=2, peak_allocated_gib=1)
            (target / 'joy_fp8_metrics.json').write_text(json.dumps(metrics))
            return metrics

        inference = Mock(side_effect=generate, load_seconds=10, details={})
        factory = Mock(return_value=inference)
        with patch.dict(sys.modules, video_inference=SimpleNamespace(VideoInference=factory)), \
             patch('research.story_eval.os.uname', return_value=SimpleNamespace(nodename='am4g1r24bm2')), \
             patch.dict('os.environ', CUDA_VISIBLE_DEVICES='3'), \
             patch('research.story_eval.subprocess.check_output', return_value=''):
            evaluation = StoryEvaluation(path, out / 'site')
            evaluation()
        factory.assert_called_once()
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0], reference.read_bytes())
        if independent:
            self.assertEqual(seen, [reference.read_bytes()] * 3)
            self.assertEqual(conditions, [(7, None), (8, None), (9, reference)])
        else:
            self.assertEqual(seen[1], (out / 'joy_fp8/0/last.png').read_bytes())
            self.assertEqual(seen[2], (out / 'joy_fp8/1/last.png').read_bytes())
        rows = evaluation.results['models'][0]['rounds']
        self.assertEqual([row['cold_seconds'] for row in rows], [12, 2, 2])
        self.assertEqual([row['first_call'] for row in rows], [True, False, False])
