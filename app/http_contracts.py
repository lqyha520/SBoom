"""文件和流式接口的 OpenAPI 声明，避免把二进制响应标为未知 JSON。"""


def binary_responses(*media_types: str, partial: bool = False) -> dict:
    return {
        status: {'content': {media: {'schema': {'type': 'string', 'format': 'binary'}} for media in media_types}}
        for status in ((200, 206) if partial else (200,))
    }
