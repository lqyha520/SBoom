"""按账号保存游戏进度，重试同一提交不重复增版。"""
import json
import time

from fastapi import HTTPException

from app.db import db
from app.game_save_validation import valid_progress
from app.models.game_progress import GameSaveInput


def item(row):
    return {key: row[key] for key in ('game_id', 'revision', 'mutation_id', 'updated_at')} | {'progress': json.loads(row['progress_json'])}


def listing(user_id):
    with db() as conn:
        return {'items': [item(row) for row in conn.execute('SELECT * FROM game_progress WHERE user_id=? ORDER BY updated_at DESC,game_id', (user_id,)).fetchall()]}


def save(user_id: int, game_id: str, body: GameSaveInput):
    if not valid_progress(game_id, body.progress):
        raise HTTPException(422, detail={'error': '游戏存档结构无效，请在游戏中重新保存', 'code': 'invalid_game_progress'})
    content = json.dumps(body.progress, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with db() as conn:
        conn.execute('INSERT INTO game_progress(user_id,game_id,progress_json,revision,mutation_id,updated_at) VALUES (?,?,?,0,?,0) ON CONFLICT DO NOTHING',
                     (user_id, game_id, '{}', ''))
        row = conn.execute('SELECT * FROM game_progress WHERE user_id=? AND game_id=? FOR UPDATE', (user_id, game_id)).fetchone()
        if row['mutation_id'] == body.mutation_id and row['progress_json'] == content:
            return item(row)
        if row['revision'] != body.revision or row['mutation_id'] == body.mutation_id:
            raise HTTPException(409, detail={'error': '另一台设备已更新进度，请选择要保留的存档', 'code': 'game_progress_conflict'})
        conn.execute('UPDATE game_progress SET progress_json=?,revision=revision+1,mutation_id=?,updated_at=? WHERE user_id=? AND game_id=?',
                     (content, body.mutation_id, int(time.time()), user_id, game_id))
        return item(conn.execute('SELECT * FROM game_progress WHERE user_id=? AND game_id=?', (user_id, game_id)).fetchone())
