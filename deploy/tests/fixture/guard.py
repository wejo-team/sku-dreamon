"""가상 모델 driver를 명시적 Docker 전용 DB에서만 허용한다."""

from collections.abc import Mapping
from urllib.parse import urlsplit


def require_fixture(environment: Mapping[str, str]) -> None:
    try:
        url = urlsplit(environment.get("DATABASE_URL", ""))
        valid = (
            environment.get("DEP03_CONTAINER_E2E") == "1"
            and environment.get("APP_ENV") == "production"
            and url.scheme == "postgresql+asyncpg"
            and url.hostname == "postgres"
            and url.path.endswith("_e2e")
            and url.port in (None, 5432)
            and not url.query
            and not url.fragment
            and not environment.get("OPENAI_API_KEY", "")
        )
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError(
            "Container fixture requires opt-in, postgres *_e2e and no key"
        )
