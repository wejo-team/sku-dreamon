"""실제 loopback 소켓과 소유한 프로세스로 실행기 격리·종료를 검증한다."""

import errno
import json
import os
import select
import signal
import socket
import subprocess
import sys
import unittest

from scripts.run_bugbash import require_unused_port, stop


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
