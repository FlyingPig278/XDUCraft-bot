"""Uvicorn lifecycle isolated from NoneBot's own server and signal handling."""

from __future__ import annotations

import asyncio
import socket
from contextlib import contextmanager
from typing import Any, Generator, Optional

import uvicorn

LOOPBACK_HOST = "127.0.0.1"
LIFECYCLE_TIMEOUT_SECONDS = 5.0


class AdminServerError(RuntimeError):
    """A fixed-code embedded server failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _EmbeddedUvicornServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        """Leave process signal ownership with NoneBot."""

        yield


class AdminServer:
    """Own the socket, Uvicorn instance, and serving task as one lifecycle."""

    def __init__(self) -> None:
        self._socket: Optional[socket.socket] = None
        self._server: Optional[_EmbeddedUvicornServer] = None
        self._task: Optional[asyncio.Task[None]] = None

    @property
    def running(self) -> bool:
        return bool(
            self._server is not None
            and self._server.started
            and self._task is not None
            and not self._task.done()
        )

    @staticmethod
    def _bound_socket(port: int) -> socket.socket:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise AdminServerError("web_admin_port_invalid")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.set_inheritable(False)
            sock.bind((LOOPBACK_HOST, port))
            sock.listen(2048)
            sock.setblocking(False)
            return sock
        except OSError:
            sock.close()
            raise AdminServerError("web_admin_bind_failed") from None

    @staticmethod
    async def _serve(server: _EmbeddedUvicornServer, sock: socket.socket) -> None:
        try:
            await server.serve(sockets=[sock])
        except SystemExit:
            # Uvicorn normally uses SystemExit for bind/config errors.  A panel
            # failure must never terminate the bot process.
            raise AdminServerError("web_admin_serve_failed") from None

    @staticmethod
    def _consume_task_result(task: asyncio.Task[None]) -> None:
        """Retrieve background exceptions even if shutdown is delayed."""

        if task.cancelled():
            return
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):
            pass

    async def start(self, app: Any, port: int) -> None:
        if self._task is not None:
            if self.running:
                raise AdminServerError("web_admin_already_running")
            await self.stop()

        sock = self._bound_socket(port)
        try:
            config = uvicorn.Config(
                app=app,
                host=LOOPBACK_HOST,
                port=port,
                workers=1,
                reload=False,
                proxy_headers=False,
                access_log=False,
                log_config=None,
                timeout_graceful_shutdown=3,
            )
            server = _EmbeddedUvicornServer(config)
            task = asyncio.create_task(
                self._serve(server, sock),
                name="xducraft-web-admin",
            )
        except Exception:
            sock.close()
            raise AdminServerError("web_admin_serve_failed") from None

        self._socket = sock
        self._server = server
        self._task = task
        task.add_done_callback(self._consume_task_result)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + LIFECYCLE_TIMEOUT_SECONDS
        try:
            while not server.started:
                if task.done():
                    try:
                        task.result()
                    except (asyncio.CancelledError, Exception):
                        pass
                    raise AdminServerError("web_admin_start_failed")
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise AdminServerError("web_admin_start_timeout")
                await asyncio.sleep(min(0.02, remaining))
        except asyncio.CancelledError:
            await self.stop()
            raise
        except Exception as exc:
            await self.stop()
            if isinstance(exc, AdminServerError):
                raise
            raise AdminServerError("web_admin_start_failed") from None

    async def stop(self) -> None:
        server = self._server
        task = self._task
        sock = self._socket

        if server is not None:
            server.should_exit = True

        failure = False
        cancelled = False
        try:
            if task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=LIFECYCLE_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                except asyncio.CancelledError:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    cancelled = True
                except Exception:
                    failure = True
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    failure = True
            self._task = None
            self._server = None
            self._socket = None

        if cancelled:
            raise asyncio.CancelledError()
        if failure:
            raise AdminServerError("web_admin_stop_failed")


_holder = AdminServer()


async def start(app: Any, port: int) -> AdminServer:
    """Start the process-wide panel server and return its holder."""

    await _holder.start(app, port)
    return _holder


async def stop() -> None:
    """Stop the process-wide panel server if it was started."""

    await _holder.stop()


__all__ = [
    "AdminServer",
    "AdminServerError",
    "LIFECYCLE_TIMEOUT_SECONDS",
    "LOOPBACK_HOST",
    "start",
    "stop",
]
