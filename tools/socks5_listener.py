"""A small SOCKS5 CONNECT listener for local, offline tests.

It speaks the no-authentication SOCKS5 handshake, records the requested target,
and tunnels the connection to a fixed local origin. That is enough to prove
that Chrome really sent traffic through SOCKS5: a bypass cannot reach the
origin through this listener, and the origin sees the real request headers.

No dependency, no third-party proxy, and it only ever listens on 127.0.0.1.
"""

from __future__ import annotations

import select
import socket
import struct
import threading
from typing import Dict, List, Tuple


class Socks5Listener:
    def __init__(self, target: Tuple[str, int]) -> None:
        self.target = target
        self.connections: List[Dict[str, object]] = []
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        self._server.listen(16)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept, daemon=True)

    def __enter__(self) -> "Socks5Listener":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=2)

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    @staticmethod
    def _read(sock: socket.socket, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("peer closed")
            data += chunk
        return data

    def _handle(self, client: socket.socket) -> None:
        origin = None
        try:
            client.settimeout(15)
            version, count = self._read(client, 2)
            methods = self._read(client, count)
            if version != 5 or 0 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x00")

            version, command, _reserved, atyp = self._read(client, 4)
            if version != 5:
                return
            if atyp == 1:
                host = socket.inet_ntoa(self._read(client, 4))
            elif atyp == 3:
                length = self._read(client, 1)[0]
                host = self._read(client, length).decode("idna")
            elif atyp == 4:
                host = socket.inet_ntop(socket.AF_INET6, self._read(client, 16))
            else:
                client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            port = struct.unpack("!H", self._read(client, 2))[0]
            self.connections.append({
                "host": host,
                "port": port,
                "atyp": atyp,
                "command": command,
                "methods": list(methods),
            })
            if command != 1:
                client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return

            origin = socket.create_connection(self.target, timeout=15)
            client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            client.settimeout(None)
            origin.settimeout(None)
            self._relay(client, origin)
        except (OSError, ConnectionError):
            pass
        finally:
            for sock in (client, origin):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

    @staticmethod
    def _relay(client: socket.socket, origin: socket.socket) -> None:
        sockets = [client, origin]
        while True:
            try:
                readable, _, _ = select.select(sockets, [], [], 20)
            except (OSError, ValueError):
                return
            if not readable:
                return
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                destination = origin if source is client else client
                destination.sendall(data)
