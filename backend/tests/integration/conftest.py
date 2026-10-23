"""환경변수로 지정한 격리 PostgreSQL의 연결 정보를 제공한다."""

import os

import pytest


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL database")
    return url
