from fastapi import HTTPException


def fail(message, status=409):
    raise HTTPException(status, detail={"error": message})
