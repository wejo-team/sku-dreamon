"""격리된 로컬 bug bash 환경의 설정·인증서·가상 공고 입력만 준비한다.

DB 생성/적재와 서버 실행은 docs/development/bug-bash.md의 명시적 명령으로 한다.
기존 backend/.env와 개발 DB에는 접근하지 않는다.
"""

import json
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".bugbash"


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    OUTPUT.mkdir(mode=0o700, exist_ok=True)
    certificate = OUTPUT / "localhost.pem"
    private_key = OUTPUT / "localhost-key.pem"
    if certificate.exists() != private_key.exists():
        raise SystemExit("인증서와 키 중 하나만 있습니다. .bugbash 파일을 확인하세요.")
    if not certificate.exists():
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(private_key),
                "-out",
                str(certificate),
                "-days",
                "30",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        private_key.chmod(0o600)
    blocklist = OUTPUT / "password-blocklist.txt"
    write_private(blocklist, "blocked-bugbash-password\n")
    backend_env = OUTPUT / "backend.env"
    # 재실행해도 실행 중 서버의 CSRF 키를 바꾸지 않는다.
    if not backend_env.exists():
        write_private(
            backend_env,
            "DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:55433/wejo_dev\n"
            f"CSRF_SIGNING_KEY={secrets.token_urlsafe(48)}\n"
            "AUTH_ALLOWED_ORIGINS='[\"https://localhost:5183\"]'\n"
            f"PASSWORD_BLOCKLIST_PATH={blocklist}\n"
            "PASSWORD_BLOCKLIST_VERSION=bugbash-fixture-v1\n"
            "AUTH_SIGNUP_IP_LIMIT=1000\n"
            "AUTH_LOGIN_IP_LIMIT=1000\n"
            "AUTH_AVAILABILITY_IP_LIMIT=1000\n"
            "OPENAI_API_KEY=\n",
        )
    write_private(
        OUTPUT / "test.env",
        "DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:55433/wejo_test\n"
        "TEST_DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:55433/wejo_test\n"
        "OPENAI_API_KEY=\n",
    )
    write_private(
        ROOT / "frontend" / ".env.bugbash",
        "VITE_API_MOCK=false\n"
        "VITE_API_BASE_URL=/api/v1\n"
        "API_PROXY_TARGET=http://127.0.0.1:8011\n"
        f"DEV_HTTPS_CERT={certificate}\n"
        f"DEV_HTTPS_KEY={private_key}\n",
    )
    now = datetime.now(UTC)
    contest = {
        "title": "Bug bash 통합검증 공모전",
        "organizer": "가상 테스트 기관",
        "sourceUrl": "https://example.com/bugbash",
        "eligibilityText": "통합테스트용 가상 공고",
        "audienceCodes": ["student"],
        "fieldCodes": ["design"],
        "capacity": {"kind": "range", "minimumMembers": "1", "maximumMembers": "4"},
        "opening": {
            "date": (now - timedelta(days=1)).date().isoformat(),
            "time": "00:00",
            "timeZone": "UTC",
        },
        "closing": {
            "date": (now + timedelta(days=30)).date().isoformat(),
            "time": "23:59",
            "timeZone": "UTC",
        },
        "verifiedAt": now.isoformat().replace("+00:00", "Z"),
        "description": "실제 모집이 아닌 자동·수동 통합검증용 자료입니다.",
        "deliverables": None,
        "awards": None,
        "contact": None,
        "posterUrl": None,
    }
    (OUTPUT / "contest.json").write_text(
        json.dumps(contest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("설정·로컬 인증서·가상 공고 입력 준비 완료: .bugbash/")
    print("DB에는 쓰지 않았습니다. docs/development/bug-bash.md 순서로 실행하세요.")


if __name__ == "__main__":
    main()
