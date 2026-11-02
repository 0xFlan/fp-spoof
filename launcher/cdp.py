"""Chrome DevTools Protocol client over ``--remote-debugging-pipe``.

Zero dependencies: the protocol is length-agnostic JSON separated by NUL bytes
on file descriptors 3 (browser -> client) and 4 (client -> browser).  This is
the same transport Puppeteer uses, and it avoids needing a WebSocket library.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
from typing import Any, Dict, List, Optional


class CDPError(RuntimeError):
    """Raised for protocol errors, timeouts and closed pipes."""


class PipeCDP:
    """Minimal synchronous CDP client bound to a debugging pipe."""

    def __init__(self, process: subprocess.Popen, read_fd: int, write_fd: int) -> None:
        self.process = process
        self._read_fd = read_fd
        self._write_fd = write_fd
        self._buffer = b""
        self._next_id = 0
        self._events: List[Dict[str, Any]] = []

    # -- transport ---------------------------------------------------------

    def _send(self, payload: Dict[str, Any]) -> None:
        try:
            os.write(self._write_fd, json.dumps(payload).encode("utf-8") + b"\x00")
        except OSError as exc:
            raise CDPError("cannot write to the browser pipe: %s" % exc) from exc

    def _read_message(self, deadline: float) -> Dict[str, Any]:
        while b"\x00" not in self._buffer:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise CDPError("timed out waiting for a response")
            ready, _, _ = select.select([self._read_fd], [], [], remaining)
            if not ready:
                raise CDPError("timed out waiting for a response")
            chunk = os.read(self._read_fd, 1 << 16)
            if not chunk:
                raise CDPError("browser closed the debugging pipe")
            self._buffer += chunk
        message, _, self._buffer = self._buffer.partition(b"\x00")
        try:
            return json.loads(message.decode("utf-8"))
        except ValueError as exc:
            raise CDPError("malformed CDP frame: %s" % exc) from exc

    # -- api ---------------------------------------------------------------

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        payload: Dict[str, Any] = {"id": message_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        self._send(payload)

        deadline = time.time() + timeout
        while True:
            message = self._read_message(deadline)
            if message.get("id") == message_id:
                if "error" in message:
                    error = message["error"]
                    raise CDPError("%s failed: %s" % (method, error.get("message", error)))
                return message.get("result", {})
            self._events.append(message)

    def evaluate(self, expression: str, session_id: Optional[str] = None, await_promise: bool = False) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            session_id=session_id,
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise CDPError("page exception: %s" % details.get("text", details))
        return result.get("result", {}).get("value")

    def wait_for(self, method: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Block until an event with ``method`` arrives."""
        for index, event in enumerate(self._events):
            if event.get("method") == method:
                return self._events.pop(index)
        deadline = time.time() + timeout
        while True:
            message = self._read_message(deadline)
            if message.get("method") == method:
                return message
            if "id" in message:
                self._events.append(message)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        for fd in (self._read_fd, self._write_fd):
            try:
                os.close(fd)
            except OSError:
                pass
