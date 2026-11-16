"""游戏云存档在一次性数据库中验证归属、版本竞争和网络重放。"""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import test_backend_library as fixtures
from fastapi import HTTPException

from app import security
from app.db import db
from app.deps import SESSION_COOKIE
from app.models.game_progress import GameSaveInput
from app.routers import games
from app.services import game_progress


class GameProgressContracts(unittest.TestCase):
    def setUp(self):
        fixtures.PaperLibraryContracts.setUp(self)
        self.client.app.include_router(games.router)

    def save_body(self, revision=0, mutation='first-mutation', day=1):
        return {'revision': revision, 'mutation_id': mutation, 'progress': {
            'version': 1, 'difficulty': 'change', 'day': day, 'customer': 0, 'stage': 'packing',
            'bag': dict.fromkeys(('apple', 'banana', 'pear', 'orange'), 0),
            'stock': dict.fromkeys(('apple', 'banana', 'pear', 'orange'), 8),
            'cash': 0, 'revenue': 0, 'profit': 0, 'mistakes': 0, 'hints': 0, 'upgrades': 0, 'lifetimeServed': 0}}

    def test_ownership_no_store_and_idempotent_replay(self):
        path = '/api/v1/me/games/little-shop'
        first = self.client.put(path, json=self.save_body())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertIn('no-store', first.headers['cache-control'])
        self.assertEqual(first.json()['revision'], 1)
        self.assertEqual(self.client.put(path, json=self.save_body()).json(), first.json())
        second = self.client.put(path, json=self.save_body(1, 'second-mutation', 2))
        self.assertEqual(second.json()['revision'], 2)
        self.assertEqual(self.client.put(path, json=self.save_body()).status_code, 409)
        self.client.cookies.set(SESSION_COOKIE, security.create_token(self.other.id))
        self.assertEqual(self.client.get('/api/v1/me/games').json(), {'items': []})
        self.assertEqual(self.client.put(path, json=self.save_body()).json()['revision'], 1)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/me/games').status_code, 401)

    def test_invalid_game_version_payload_and_mutation_reuse(self):
        path = '/api/v1/me/games/little-shop'
        self.assertEqual(self.client.put('/api/v1/me/games/unknown', json=self.save_body()).status_code, 422)
        for content in ({'version': 2}, {'version': True}, {'version': 1}, {'version': 1, 'data': '大' * 50000},
                        self.save_body()['progress'] | {'day': True}, self.save_body()['progress'] | {'bag': []}):
            self.assertEqual(self.client.put(path, json=self.save_body() | {'progress': content}).status_code, 422)
        self.assertEqual(self.client.get('/api/v1/me/games').json(), {'items': []})
        self.assertEqual(self.client.put('/api/v1/me/games/robot-maze', json=self.save_body()).status_code, 422)
        self.client.put(path, json=self.save_body())
        self.assertEqual(self.client.put(path, json=self.save_body(1, day=2)).status_code, 409)

    def test_concurrent_devices_do_not_overwrite_and_account_deletion_cascades(self):
        game_progress.save(self.user.id, 'little-shop', GameSaveInput(**self.save_body()))

        def attempt(number):
            try:
                return game_progress.save(self.user.id, 'little-shop', GameSaveInput(**self.save_body(1, f'device-{number}', number)))['revision']
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(attempt, [2, 3])), [2, 409])
        with db() as conn:
            conn.execute('DELETE FROM users WHERE id=?', (self.user.id,))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM game_progress WHERE user_id=?', (self.user.id,)).fetchone()[0], 0)

    def test_real_frontend_saves_are_accepted_and_malformed_updates_preserve_previous_version(self):
        examples = json.loads((Path(__file__).parent / 'fixtures' / 'game-progress.json').read_text(encoding='utf-8'))
        for game_id, progress in examples.items():
            path = '/api/v1/me/games/' + game_id
            body = {'revision': 0, 'mutation_id': 'valid-fixture', 'progress': progress}
            saved = self.client.put(path, json=body)
            self.assertEqual(saved.status_code, 200, saved.text)
            for malformed in ({'version': 1}, progress | {'difficulty': 'unsupported'} if game_id != 'robot-maze' else progress | {'program': [{}]}):
                failed = self.client.put(path, json=body | {'revision': 1, 'mutation_id': 'invalid-fixture', 'progress': malformed})
                self.assertEqual(failed.status_code, 422, failed.text)
        stored = self.client.get('/api/v1/me/games').json()['items']
        self.assertEqual(len(stored), 10)
        self.assertTrue(all(item['revision'] == 1 and item['progress'] == examples[item['game_id']] for item in stored))


if __name__ == '__main__':
    unittest.main()
