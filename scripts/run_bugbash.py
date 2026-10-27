"""준비된 DB에서 HTTPS E2E를 실행하고 직접 시작한 서버만 종료한다."""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def available_port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("포트는 1~65535여야 합니다.")
    return port


def require_unused_port(port: int) -> None:
    for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family) as listener:
                # 직전 실행의 TIME_WAIT는 새 listener의 사용을 막는 충돌이 아니다.
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((address, port))
        except OSError as error:
            if family == socket.AF_INET6 and error.errno in {
                errno.EAFNOSUPPORT,
                errno.EADDRNOTAVAIL,
            }:
                continue
            raise RuntimeError(
                f"포트 {port}를 사용할 수 없습니다. 다른 포트를 지정하세요."
            ) from None


def stop(process: subprocess.Popen[bytes], grace_seconds: float = 10) -> None:
    # npm/uv가 시작한 자식도 정리하되 다른 실행의 프로세스에는 신호를 보내지 않는다.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def wait_ready(url: str, processes: list[subprocess.Popen[bytes]]) -> None:
    deadline = time.monotonic() + 40
    # localhost 자체 서명 인증서에만 사용한다. 외부 URL은 인자로 받지 않는다.
    context = ssl._create_unverified_context()
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("서버가 준비 전에 종료됐습니다. 실행 로그를 확인하세요.")
        try:
            with urlopen(url, timeout=2, context=context) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError("서버 준비 시간이 초과됐습니다. 실행 로그를 확인하세요.")


def interrupted(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-env", type=Path, default=ROOT / ".bugbash/backend.env"
    )
    parser.add_argument("--backend-port", type=available_port, default=8011)
    parser.add_argument("--frontend-port", type=available_port, default=5183)
    parser.add_argument(
        "--certificate", type=Path, default=ROOT / ".bugbash/localhost.pem"
    )
    parser.add_argument(
        "--private-key", type=Path, default=ROOT / ".bugbash/localhost-key.pem"
    )
    parser.add_argument("playwright_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("이 실행기는 Linux/macOS/WSL에서 사용합니다.")
    for path in (args.backend_env, args.certificate, args.private_key):
        if not path.is_file():
            parser.error(f"준비 파일이 없습니다: {path}")
    if args.backend_port == args.frontend_port:
        parser.error("백엔드와 프론트 포트는 달라야 합니다.")
    try:
        require_unused_port(args.backend_port)
        require_unused_port(args.frontend_port)
    except RuntimeError as error:
        parser.error(str(error))

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S-%fZ")
    output = ROOT / ".bugbash" / "runs" / run_id
    output.mkdir(parents=True, mode=0o700)
    origin = f"https://localhost:{args.frontend_port}"
    environment = os.environ.copy()
    for name in list(environment):
        if name.upper() in {"DATABASE_URL", "TEST_DATABASE_URL", "OPENAI_API_KEY"}:
            environment.pop(name)
    # 비AI 실행기는 셸이나 env 파일의 모델 키를 사용하지 않는다.
    environment.update(
        OPENAI_API_KEY="",
        TEST_DATABASE_URL="",
        AUTH_ALLOWED_ORIGINS=json.dumps([origin]),
        E2E_BASE_URL=origin,
        E2E_ARTIFACT_DIR=str(output),
        API_PROXY_TARGET=f"http://127.0.0.1:{args.backend_port}",
        DEV_HTTPS_CERT=str(args.certificate.resolve()),
        DEV_HTTPS_KEY=str(args.private_key.resolve()),
        VITE_API_MOCK="false",
        VITE_API_BASE_URL="/api/v1",
    )
    backend_prefix = ["uv", "run", "--env-file", str(args.backend_env.resolve())]
    # 설정 누락·대소문자 별칭 때문에 다른 DB나 모델 키로 실행하지 않는다.
    check = subprocess.run(
        backend_prefix
        + [
            "python",
            "-c",
            "import os, sys\nfrom sqlalchemy.engine import make_url\n"
            "from app.core.config import Settings\n"
            "a=make_url(os.environ['DATABASE_URL'])\n"
            "settings=Settings()\n"
            "valid = (not a.query and a.drivername == 'postgresql+asyncpg' "
            "and a.host in {'localhost','127.0.0.1','::1'} and bool(a.database) "
            "and make_url(str(settings.database_url)) == a "
            "and not settings.openai_api_key)\n"
            "if os.environ.get('E2E_MIXED_DATA') == '1':\n"
            " b=make_url(os.environ.get('E2E_MIXED_DATABASE_URL',''))\n"
            " valid = valid and a == b and a.database.endswith('_e2e')\n"
            "sys.exit(0 if valid else 1)",
        ],
        cwd=ROOT / "backend",
        env=environment,
        capture_output=True,
    )
    if check.returncode:
        parser.error(
            "env 파일의 명시적 localhost DATABASE_URL과 실제 설정이 같고 "
            "AI 키가 비어 있어야 합니다. 혼합 검사는 같은 *_e2e 복제 DB만 허용합니다."
        )
    # 직접 npm 실행이 다른 원본 서버에 시연 계정으로 쓰지 못하게 한다.
    # 부모 셸에는 남기지 않고 검증한 자식 실행에만 전달한다.
    environment.pop("E2E_MIXED_VERIFIED_BASE_URL", None)
    if environment.get("E2E_MIXED_DATA") == "1":
        environment["E2E_MIXED_VERIFIED_BASE_URL"] = origin

    processes: list[subprocess.Popen[bytes]] = []
    result = 1
    previous_sigterm = signal.signal(signal.SIGTERM, interrupted)
    try:
        with (
            (output / "backend.log").open("wb") as backend_log,
            (output / "frontend.log").open("wb") as frontend_log,
        ):
            processes.append(
                subprocess.Popen(
                    backend_prefix
                    + [
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.backend_port),
                        "--no-access-log",
                    ],
                    cwd=ROOT / "backend",
                    env=environment,
                    stdout=backend_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
            wait_ready(f"http://127.0.0.1:{args.backend_port}/api/v1/health", processes)
            processes.append(
                subprocess.Popen(
                    [
                        "npm",
                        "run",
                        "dev",
                        "--",
                        "--mode",
                        "bugbash",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.frontend_port),
                        "--strictPort",
                    ],
                    cwd=ROOT / "frontend",
                    env=environment,
                    stdout=frontend_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
            # health만 성공하는 DB 미준비 상태도 브라우저를 열기 전에 실패시킨다.
            for route in ("/catalogs", "/contests?pageSize=1", "/auth/csrf"):
                wait_ready(f"{origin}/api/v1{route}", processes)
            arguments = args.playwright_args
            if arguments[:1] == ["--"]:
                arguments = arguments[1:]
            print(f"E2E 준비 완료: {origin}\n결과 경로: {output}", flush=True)
            runner = subprocess.Popen(
                ["npm", "run", "test:e2e", "--", *arguments],
                cwd=ROOT / "frontend",
                env=environment,
                start_new_session=True,
            )
            processes.append(runner)
            result = runner.wait()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
    except KeyboardInterrupt:
        result = 130
    finally:
        # 종료 처리 중 추가 신호가 와도 소유한 프로세스 정리를 마친다.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        previous_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
        for process in reversed(processes):
            stop(process)
        (output / "execution.json").write_text(
            json.dumps(
                {
                    "baseURL": origin,
                    "exitCode": result,
                    "mixedData": environment.get("E2E_MIXED_DATA") == "1",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"실행한 서버 종료 완료. 로그·결과: {output}", flush=True)
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
