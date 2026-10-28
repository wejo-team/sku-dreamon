"""브라우저용 가짜 모델은 명시적인 격리 DB에서만 시작한다."""

import pytest

from app import main
from tests.e2e_ai_app import FixtureDriver, create_app


@pytest.fixture
def fixture_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_AI_FIXTURE", "1")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/test_e2e"
    )
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("E2E_AI_FIXTURE", "0"),
        ("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/wejo_dev"),
        ("DATABASE_URL", "postgresql+asyncpg://u:p@example.com/test_e2e"),
        ("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test_e2e?host=remote"),
        ("OPENAI_API_KEY", "synthetic-key-must-not-be-used"),
    ],
)
def test_rejects_unsafe_configuration_before_creating_app(
    fixture_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="AI E2E"):
        create_app()


def test_requires_explicit_database_url(
    fixture_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(RuntimeError, match="AI E2E"):
        create_app()


async def test_fake_driver_uses_real_lifespan_and_never_constructs_provider(
    fixture_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_provider(*args: object, **kwargs: object) -> None:
        pytest.fail("A real model provider must never be constructed")

    monkeypatch.setattr(main, "OpenAiAgentDriver", forbidden_provider)
    app = create_app()
    # 포트 1에는 DB가 없다. 앱 시작 자체는 SQL이나 모델 호출을 하지 않는다.
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.ai_driver, FixtureDriver)
        assert app.state.database is not None
    # 제품 종료는 실제 모델 client를 닫으므로 먼저 원래 None을 복원해야 한다.
    assert app.state.ai_driver is None
