"""실제 loopback 소켓과 소유한 프로세스로 실행기 격리·종료를 검증한다."""

import errno
import json
import os
import select
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import run_bugbash
from scripts.run_bugbash import require_unused_port, stop


class PlaywrightArgumentTests(unittest.TestCase):
    def test_preserves_scenario_selection(self):
        self.assertEqual(
            run_bugbash.playwright_arguments(["--", "--project=chromium", "browse"]),
            ["--project=chromium", "browse"],
        )

    def test_rejects_config_overrides_that_remove_global_setup(self):
        for arguments in (
            ["--", "--config", "unverified.config.ts"],
            ["--config=unverified.config.ts"],
            ["-c", "unverified.config.ts"],
            ["-cunverified.config.ts"],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                run_bugbash.playwright_arguments(arguments)


@unittest.skipUnless(os.name == "posix", "The bug bash runner requires POSIX")
class AiFixtureBoundaryTests(unittest.TestCase):
    def run_fixture(self, *, selected=False, valid=True, change_file_after_check=False):
        # 실패 시 런타임을 시작하지 않는지와 자식의 실제 실행 인자·환경을 확인한다.
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            files = [root / name for name in ("backend.env", "cert.pem", "key.pem")]
            for file in files:
                file.touch()
            argv = [
                "run_bugbash.py",
                "--backend-env",
                str(files[0]),
                "--certificate",
                str(files[1]),
                "--private-key",
                str(files[2]),
                *(["--ai-fixture"] if selected else []),
            ]
            stack.enter_context(patch.object(run_bugbash, "ROOT", root))
            stack.enter_context(patch.object(sys, "argv", argv))
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "E2E_AI_FIXTURE": "1",
                        "e2e_ai_fixture": "1",
                        "E2E_AI_VERIFIED_BASE_URL": "https://unverified.invalid",
                        "e2e_ai_verified_base_url": "https://unverified.invalid",
                        "E2E_VERIFIED_BASE_URL": "https://localhost:5183",
                        "e2e_verified_base_url": "https://localhost:5183",
                        "E2E_VERIFIED_BACKEND_URL": "http://127.0.0.1:8011",
                        "API_PROXY_TARGET": "http://127.0.0.1:8011",
                        "api_proxy_target": "http://127.0.0.1:8011",
                        "VITE_API_BASE_URL": "https://localhost:5183/api/v1",
                        "vite_api_base_url": "https://localhost:5183/api/v1",
                        "VITE_API_MOCK": "true",
                        "database_url": "inherited-database",
                        "openai_api_key": "synthetic-inherited-key",
                    },
                    clear=True,
                )
            )
            stack.enter_context(patch.object(run_bugbash, "require_unused_port"))
            database_url = "postgresql+asyncpg://wejo:synthetic@127.0.0.1/guard_e2e"

            def checked_environment(*_args, **_kwargs):
                if change_file_after_check:
                    files[0].write_text(
                        "DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1/wejo_dev\n"
                    )
                return Mock(
                    returncode=0 if valid else 1,
                    stdout=json.dumps({"databaseUrl": database_url}).encode(),
                )

            check = stack.enter_context(
                patch.object(
                    run_bugbash.subprocess,
                    "run",
                    side_effect=checked_environment,
                )
            )
            child = Mock()
            child.wait.return_value = 0
            start = stack.enter_context(
                patch.object(run_bugbash.subprocess, "Popen", return_value=child)
            )
            stack.enter_context(patch.object(run_bugbash, "wait_ready"))
            stack.enter_context(patch.object(run_bugbash, "stop"))
            if valid:
                self.assertEqual(run_bugbash.main(), 0)
            else:
                with self.assertRaises(SystemExit) as raised:
                    run_bugbash.main()
                self.assertEqual(raised.exception.code, 2)
                start.assert_not_called()
            return check.call_args.kwargs["env"], start.call_args_list

    def test_inherited_ai_flags_and_case_aliases_cannot_select_fixture(self):
        environment, calls = self.run_fixture()
        self.assertEqual(environment["E2E_AI_FIXTURE"], "0")
        self.assertEqual(environment["OPENAI_API_KEY"], "")
        for key in (
            "database_url",
            "openai_api_key",
            "e2e_ai_fixture",
            "e2e_ai_verified_base_url",
            "E2E_AI_VERIFIED_BASE_URL",
            "e2e_verified_base_url",
            "api_proxy_target",
            "vite_api_base_url",
        ):
            self.assertNotIn(key, environment)
        self.assertIn("tests.e2e_app:create_app", calls[0].args[0])
        self.assertIn("--factory", calls[0].args[0])

    def test_all_browser_runs_get_verified_and_owned_targets(self):
        environment, calls = self.run_fixture()
        self.assertEqual(environment["E2E_BASE_URL"], "https://localhost:5185")
        self.assertEqual(
            environment["E2E_VERIFIED_BASE_URL"], environment["E2E_BASE_URL"]
        )
        self.assertEqual(environment["API_PROXY_TARGET"], "http://127.0.0.1:8013")
        self.assertEqual(
            environment["E2E_VERIFIED_BACKEND_URL"], environment["API_PROXY_TARGET"]
        )
        self.assertEqual(environment["VITE_API_BASE_URL"], "/api/v1")
        self.assertEqual(environment["VITE_API_MOCK"], "false")
        self.assertEqual(len(calls), 3)
        self.assertNotIn("DATABASE_URL", environment)
        self.assertEqual(
            calls[0].kwargs["env"]["DATABASE_URL"],
            "postgresql+asyncpg://wejo:synthetic@127.0.0.1/guard_e2e",
        )
        for call in calls[1:]:
            self.assertIs(call.kwargs["env"], environment)

    def test_file_change_after_preflight_cannot_redirect_backend_to_development(self):
        environment, calls = self.run_fixture(change_file_after_check=True)
        self.assertEqual(
            calls[0].kwargs["env"]["DATABASE_URL"],
            "postgresql+asyncpg://wejo:synthetic@127.0.0.1/guard_e2e",
        )
        self.assertNotIn("DATABASE_URL", environment)

    def test_explicit_ai_option_uses_only_test_factory_after_preflight(self):
        environment, calls = self.run_fixture(selected=True)
        self.assertEqual(environment["E2E_AI_FIXTURE"], "1")
        self.assertEqual(
            environment["E2E_AI_VERIFIED_BASE_URL"], environment["E2E_BASE_URL"]
        )
        self.assertIn("tests.e2e_ai_app:create_app", calls[0].args[0])
        self.assertIn("--factory", calls[0].args[0])

    def test_rejected_ai_preflight_starts_no_servers_or_browser(self):
        self.run_fixture(selected=True, valid=False)

    def test_rejected_basic_preflight_starts_no_servers_or_browser(self):
        self.run_fixture(valid=False)


@unittest.skipUnless(os.name == "posix", "The bug bash runner requires POSIX")
class PortGuardTests(unittest.TestCase):
    def assert_listener_is_preserved(self, family, address):
        try:
            listener = socket.socket(family)
            self.addCleanup(listener.close)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((address, 0))
        except OSError as error:
            if family == socket.AF_INET6 and error.errno in {
                errno.EAFNOSUPPORT,
                errno.EADDRNOTAVAIL,
                errno.EPROTONOSUPPORT,
            }:
                self.skipTest("IPv6 loopback is unavailable")
            raise
        listener.listen()
        listener.settimeout(3)
        port = listener.getsockname()[1]

        with self.assertRaises(RuntimeError):
            require_unused_port(port)

        # 충돌 검사가 기존 listener를 닫거나 교체하지 않았는지도 확인한다.
        with socket.socket(family) as client:
            client.settimeout(3)
            client.connect((address, port))
            connection, _ = listener.accept()
            with connection:
                connection.sendall(b"p")
                self.assertEqual(client.recv(1), b"p")

    def test_rejects_existing_ipv4_listener_without_interrupting_it(self):
        self.assert_listener_is_preserved(socket.AF_INET, "127.0.0.1")

    @unittest.skipUnless(socket.has_ipv6, "IPv6 is unavailable")
    def test_rejects_existing_ipv6_listener_without_interrupting_it(self):
        self.assert_listener_is_preserved(socket.AF_INET6, "::1")

    def test_allows_restart_while_previous_connection_is_in_time_wait(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(3)
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    # 서버가 먼저 FIN을 보내야 서버 포트에 TIME_WAIT가 남는다.
                    connection.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(connection.recv(1), b"")

        with socket.socket() as without_reuse:
            with self.assertRaises(OSError) as raised:
                without_reuse.bind(("127.0.0.1", port))
            self.assertEqual(raised.exception.errno, errno.EADDRINUSE)

        require_unused_port(port)
        with socket.socket() as restarted:
            restarted.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            restarted.bind(("127.0.0.1", port))
            restarted.listen()


@unittest.skipUnless(os.name == "posix", "Process groups require POSIX")
class ProcessCleanupTests(unittest.TestCase):
    def test_stops_term_resistant_child_after_its_parent_exits(self):
        program = """
import json
import os
import signal
import socket
import time

signal.signal(signal.SIGTERM, signal.SIG_DFL)
if os.fork() == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        print(json.dumps({"port": listener.getsockname()[1]}), flush=True)
        while True:
            connection, _ = listener.accept()
            connection.close()
else:
    while True:
        time.sleep(60)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", program],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        def cleanup():
            # 실패해도 테스트가 직접 만든 그룹만 제거한다.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)

        self.addCleanup(cleanup)
        ready, _, _ = select.select([process.stdout], [], [], 5)
        self.assertTrue(ready, "The child did not open its listener")
        line = process.stdout.readline()
        self.assertTrue(line, "The child exited before reporting readiness")
        port = json.loads(line)["port"]
        with self.assertRaises(RuntimeError):
            require_unused_port(port)

        stop(process, grace_seconds=0.2)

        # 자식도 stdout을 보유하므로 EOF는 부모만 종료해서는 도착하지 않는다.
        _, errors = process.communicate(timeout=3)
        self.assertEqual(errors, b"")
        self.assertEqual(process.returncode, -signal.SIGTERM)
        require_unused_port(port)
        with socket.socket() as replacement:
            replacement.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            replacement.bind(("127.0.0.1", port))
            replacement.listen()


if __name__ == "__main__":
    unittest.main()
