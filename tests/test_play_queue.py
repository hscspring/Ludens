import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from pipeline.tavern.api import TavernService
from pipeline.tavern.play_queue import PlayQueue
from pipeline.tavern.router import TavernApp


class PlayQueueTest(unittest.TestCase):
    def test_capacity_order_and_disconnection(self) -> None:
        queue = PlayQueue()
        with patch('pipeline.tavern.play_queue.time.monotonic', return_value=0):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(queue.touch, map(str, range(8))))
            self.assertEqual(sum(result['admitted'] for result in results), 2)
            order = list(queue.tickets)
            self.assertEqual(queue.touch(order[3])['position'], 2)
            queue.leave(order[0])
            self.assertTrue(queue.touch(order[2])['admitted'])
            self.assertEqual(queue.touch(order[3])['position'], 1)
        with patch('pipeline.tavern.play_queue.time.monotonic', return_value=100):
            queue.touch(order[3])
            queue.touch(order[4])
        with patch('pipeline.tavern.play_queue.time.monotonic', return_value=121):
            self.assertFalse(queue.admitted(order[1]))
            self.assertTrue(queue.touch(order[3])['admitted'])
            self.assertTrue(queue.touch(order[4])['admitted'])
            self.assertEqual(queue.touch('newcomer')['position'], 1)

    def test_waiting_player_cannot_start_or_act(self) -> None:
        with patch.dict(os.environ, {'LUDENS_LIVE': '0'}):
            service = TavernService()
        service.story = True
        with TestClient(TavernApp(service).app) as client:
            for ticket in ('one', 'two', 'three'):
                client.post(f'/api/play/{ticket}')
            self.assertEqual(client.post('/api/session').status_code, 429)
            headers = {'X-Play-Ticket': 'three'}
            self.assertEqual(client.post('/api/session', headers=headers).status_code, 429)
            admitted = {'X-Play-Ticket': 'one'}
            response = client.post('/api/session', headers=admitted)
            self.assertEqual(response.status_code, 200)
            session_id = response.json()['id']
            for path in ('act', 'events/1/video', 'replay', 'playback'):
                self.assertEqual(client.post(f'/api/session/{session_id}/{path}', headers=headers).status_code, 429)
            client.post('/api/play/one/leave')
            self.assertTrue(client.post('/api/play/three').json()['admitted'])
            self.assertEqual(client.post('/api/session', headers=headers).status_code, 200)
            self.assertEqual(client.post('/api/session', headers=admitted).status_code, 429)
