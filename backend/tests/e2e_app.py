"""비AI 브라우저 검사도 서버 시작 시 실제 격리 DB 설정을 다시 확인한다."""

import os

from fastapi import FastAPI
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app as create_product_app
from tests.database_guard import isolated_database_url


def create_app() -> FastAPI:
    settings = Settings()
    try:
        explicit = isolated_database_url(
            os.environ.get("DATABASE_URL", ""), suffix="_e2e"
        )
    except ValueError:
        raise RuntimeError(
            "Browser E2E requires an explicit localhost *_e2e DB"
        ) from None
    if make_url(str(settings.database_url)) != explicit or settings.openai_api_key:
        raise RuntimeError("Browser E2E settings changed after verification")
    # 검증한 설정 객체를 넘겨 제품 앱이 환경 파일을 다시 읽지 않게 한다.
    return create_product_app(settings)
