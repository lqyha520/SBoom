from fastapi import HTTPException


def fail(message, status=409, code=""):
    raise HTTPException(status, detail={"error": message, **({"code": code} if code else {})})
