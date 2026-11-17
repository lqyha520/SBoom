"""工作台游戏云存档；访客游戏不依赖这些接口。"""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_user
from app.library_deps import no_store
from app.models.game_progress import GameId, GameSave, GameSaveInput, GameSaves
from app.services import game_progress
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix='/api/v1/me/games', tags=['学习游戏'], dependencies=[Depends(no_store)])


@router.get('', response_model=GameSaves)
def list_saves(user: CurrentUser = Depends(require_user)):
    return game_progress.listing(user.id)


@router.put('/{game_id}', response_model=GameSave)
def save_game(game_id: GameId, body: GameSaveInput, user: CurrentUser = Depends(require_user)):
    if not allow(f'game-save:{user.id}', 120, 60):
        raise HTTPException(429, detail={'error': '保存过于频繁，请稍后重试'})
    return game_progress.save(user.id, game_id, body)
