from typing import NoReturn

from fastapi import HTTPException


def fail(message: str, status: int = 409, code: str = "") -> NoReturn:
    raise HTTPException(status, detail={"error": message, **({"code": code} if code else {})})
