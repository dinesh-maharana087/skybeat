"""Bounded subprocess execution for the fixed NVIDIA query only."""

import asyncio
import os
import signal
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

MAX_OUTPUT_BYTES = 65536
TERMINATION_GRACE_SECONDS = 0.25


@dataclass(frozen=True)
class ProcessResult:
    output: bytes
    error: bytes
    returncode: int | None
    reason: str | None = None


class _CapturedOutput:
    def __init__(self) -> None:
        self.output = bytearray()
        self.error = bytearray()
        self.overflow = asyncio.Event()

    def append(self, target: bytearray, chunk: bytes) -> None:
        remaining = MAX_OUTPUT_BYTES - len(self.output) - len(self.error)
        if remaining > 0:
            target.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.overflow.set()


class BoundedProcess:
    def __init__(self) -> None:
        self._active: asyncio.subprocess.Process | None = None

    async def run(self, args: Sequence[str], timeout: float) -> ProcessResult:
        if self._active is not None and self._active.returncode is None:
            return ProcessResult(b"", b"", None, "collector_stuck")
        try:
            if os.name == "posix":
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                    start_new_session=True,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                )
        except FileNotFoundError:
            return ProcessResult(b"", b"", None, "command_missing")
        except PermissionError:
            return ProcessResult(b"", b"", None, "permission_denied")
        self._active = process
        captured = _CapturedOutput()

        async def read_stream(stream: asyncio.StreamReader | None, target: bytearray) -> None:
            if stream is None:
                return
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    return
                if not captured.overflow.is_set():
                    captured.append(target, chunk)

        readers = [
            asyncio.create_task(read_stream(process.stdout, captured.output)),
            asyncio.create_task(read_stream(process.stderr, captured.error)),
        ]

        async def complete() -> None:
            await asyncio.gather(process.wait(), *readers)

        completed = asyncio.create_task(complete())
        overflowed = asyncio.create_task(captured.overflow.wait())
        reason: str | None = None
        try:
            done, _ = await asyncio.wait(
                {completed, overflowed}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if overflowed in done:
                reason = "output_limit"
            elif completed not in done:
                reason = "timeout"
            if reason is not None and not await self._stop(process):
                reason = "collector_stuck"
        except asyncio.CancelledError:
            await self._stop(process)
            raise
        finally:
            overflowed.cancel()
            await asyncio.gather(overflowed, return_exceptions=True)
            if reason is not None:
                await self._finish_readers(readers)
            try:
                await asyncio.wait_for(asyncio.shield(completed), timeout=TERMINATION_GRACE_SECONDS)
            except TimeoutError:
                completed.cancel()
                await asyncio.gather(completed, return_exceptions=True)
            if process.returncode is not None:
                self._active = None
        output = bytes(captured.output)
        error = bytes(captured.error)
        if reason is not None:
            return ProcessResult(output, error, process.returncode, reason)
        if process.returncode:
            return ProcessResult(output, error, process.returncode, "nonzero_exit")
        return ProcessResult(output, error, process.returncode)

    async def close(self) -> None:
        if self._active and self._active.returncode is None:
            await self._stop(self._active)
        if self._active and self._active.returncode is not None:
            self._active = None

    async def _finish_readers(self, readers: list[asyncio.Task[None]]) -> None:
        try:
            await asyncio.wait_for(asyncio.gather(*readers), timeout=TERMINATION_GRACE_SECONDS)
        except TimeoutError:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)

    async def _stop(self, process: asyncio.subprocess.Process) -> bool:
        if process.returncode is not None:
            return True
        self._signal(process, force=False)
        try:
            await asyncio.wait_for(process.wait(), timeout=TERMINATION_GRACE_SECONDS)
            return True
        except TimeoutError:
            self._signal(process, force=True)
            try:
                await asyncio.wait_for(process.wait(), timeout=TERMINATION_GRACE_SECONDS)
                return True
            except TimeoutError:
                return False

    @staticmethod
    def _signal(process: asyncio.subprocess.Process, *, force: bool) -> None:
        if os.name == "posix":
            try:
                killpg = cast(Callable[[int, int], None], getattr(os, "killpg"))  # noqa: B009
                killpg(process.pid, getattr(signal, "SIGKILL" if force else "SIGTERM"))
                return
            except ProcessLookupError:
                return
        if force:
            process.kill()
        else:
            process.terminate()
