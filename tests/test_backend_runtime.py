"""Local startup rejects old listeners instead of mixing backend versions."""

import socket
import unittest

from run import ensure_port_available


class RuntimeContracts(unittest.TestCase):
    def test_reused_listener_port_is_rejected(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as existing:
            existing.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            existing.bind(("127.0.0.1", 0))
            existing.listen()
            with self.assertRaisesRegex(SystemExit, "Stop the existing service"):
                ensure_port_available("127.0.0.1", existing.getsockname()[1])

    def test_port_probe_releases_its_socket(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        ensure_port_available("127.0.0.1", port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", port))
