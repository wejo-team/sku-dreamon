"""생성 요청의 정규화 본문을 안정된 지문으로 비교한다."""

import hashlib
import json


def request_fingerprint(body: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
