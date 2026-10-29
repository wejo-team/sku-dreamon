"""실제 DB 없이 공유 TLS·pool 예산과 CA·호스트명 검증을 확인한다."""

import shutil
import ssl
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import PostgresDsn
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.db.session import create_database, create_engine


@pytest.fixture
def certificate(tmp_path: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("Synthetic TLS handshake requires openssl")
    certificate = tmp_path / "synthetic-cert.pem"
    key = tmp_path / "synthetic-key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "2",
            "-subj",
            "/CN=db.example.com",
            "-addext",
            "subjectAltName=DNS:db.example.com",
        ],
        check=True,
        capture_output=True,
    )
    return certificate, key


def connection_settings(certificate: Path | None = None) -> Settings:
    return Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://synthetic:synthetic@db.example.com/app"
        ),
        database_tls_ca_file=certificate,
        _env_file=None,
    )


@pytest.mark.parametrize("pooled", [True, False])
def test_shared_engine_has_verified_tls_and_all_budgets(
    monkeypatch: pytest.MonkeyPatch, certificate: tuple[Path, Path], pooled: bool
) -> None:
    factory = Mock()
    monkeypatch.setattr("app.core.db.session.create_async_engine", factory)
    settings = connection_settings(certificate[0])
    create_engine(settings, pooled=pooled)
    kwargs = factory.call_args.kwargs
    arguments = kwargs["connect_args"]
    assert arguments["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert arguments["ssl"].check_hostname is True
    assert arguments["timeout"] == 3
    assert arguments["command_timeout"] == 10
    assert arguments["server_settings"] == {
        "statement_timeout": "10000",
        "lock_timeout": "2000",
        "idle_in_transaction_session_timeout": "15000",
    }
    if pooled:
        assert (
            kwargs["pool_size"],
            kwargs["max_overflow"],
            kwargs["pool_timeout"],
        ) == (3, 2, 3)
    else:
        assert kwargs["poolclass"] is NullPool


def handshake(
    client_context: ssl.SSLContext, server_context: ssl.SSLContext, hostname: str
) -> None:
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(client_in, client_out, server_hostname=hostname)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    # 메모리 안에서 TLS 왕복을 전달하여 포트나 외부 네트워크 없이 검증한다.
    for _ in range(10):
        try:
            client.do_handshake()
            return
        except ssl.SSLWantReadError:
            server_in.write(client_out.read())
        try:
            server.do_handshake()
        except ssl.SSLWantReadError:
            pass
        client_in.write(server_out.read())
    pytest.fail("TLS handshake did not finish")


def test_tls_rejects_wrong_hostname_and_untrusted_ca(
    monkeypatch: pytest.MonkeyPatch, certificate: tuple[Path, Path]
) -> None:
    factory = Mock()
    monkeypatch.setattr("app.core.db.session.create_async_engine", factory)
    create_engine(connection_settings(certificate[0]))
    client_context = factory.call_args.kwargs["connect_args"]["ssl"]
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certificate[0]), str(certificate[1]))
    handshake(client_context, server_context, "db.example.com")
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(client_context, server_context, "wrong.example.com")
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(ssl.create_default_context(), server_context, "db.example.com")


def test_invalid_ca_fails_before_any_database_connection(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-ca.pem"
    invalid.write_text("synthetic invalid certificate")
    with pytest.raises(ssl.SSLError):
        create_engine(connection_settings(invalid))


async def test_create_database_url_only_keeps_compatibility() -> None:
    database = create_database("postgresql+asyncpg://synthetic:synthetic@192.0.2.1/app")
    await database.engine.dispose()
