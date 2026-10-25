"""일반 입력 텍스트를 NFC·코드 포인트 기준으로 검증한다."""

import unicodedata


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if "\x00" in value:
        raise ValueError("NUL is not supported")
    value.encode("utf-8")
    return value
