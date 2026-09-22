"""Bounded subprocess execution for the fixed NVIDIA query only."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    output: bytes
    error: bytes
    returncode: int | None
    reason: str | None = None


class BoundedProcess:
    def __init__(self) -> None:
        self._active: asyncio.subprocess.Process | None = None

    async def run(self, args: Sequence[str], timeout: float) -> ProcessResult:
        try:
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
        try:
            output, error = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return ProcessResult(b"", b"", None, "timeout")
        finally:
            self._active = None
        if len(output) + len(error) > 65536:
            return ProcessResult(
                output[:65536],
                error[: max(0, 65536 - len(output[:65536]))],
                process.returncode,
                "output_limit",
            )
        if process.returncode:
            return ProcessResult(output, error, process.returncode, "nonzero_exit")
        return ProcessResult(output, error, process.returncode)

    async def close(self) -> None:
        if self._active and self._active.returncode is None:
            self._active.kill()
            await self._active.wait()
