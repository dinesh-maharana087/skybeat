"""Safe NVIDIA inventory collection with finite wire reason codes."""

import csv
import io
from typing import Any

from skybeat_agent.collectors.process import BoundedProcess

QUERY = (
    "--query-gpu=index,uuid,name,utilization.gpu,temperature.gpu,"
    "memory.total,memory.used,driver_version"
)
FORMAT = "--format=csv,noheader,nounits"


def failed(reason: str, *, state: str = "NVIDIA_SMI_FAILED") -> dict[str, Any]:
    return {
        "gpu_health": {"state": state, "reason_code": reason, "inventory_reliable": False},
        "gpus": [],
    }


def _metric(value: str, maximum: float) -> float | None:
    if value == "N/A":
        return None
    number = float(value)
    if not 0 <= number <= maximum:
        raise ValueError
    return number


def parse_gpu_output(output: bytes) -> dict[str, Any]:
    if len(output) > 65536:
        return failed("output_limit")
    try:
        text = output.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text), skipinitialspace=True))
        rows = [row for row in rows if row]
        if not rows:
            return {
                "gpu_health": {
                    "state": "GPU_MISSING",
                    "reason_code": "no_gpu",
                    "inventory_reliable": True,
                },
                "gpus": [],
            }
        if len(rows) > 64:
            return failed("output_limit")
        gpus: list[dict[str, Any]] = []
        for row in rows:
            if len(row) != 8:
                raise ValueError
            index = int(row[0])
            if not 0 <= index <= 1023 or not row[1] or len(row[1]) > 96:
                raise ValueError
            utilization = _metric(row[3], 100)
            temperature = _metric(row[4], 250)
            total_mib = _metric(row[5], 24576)
            used_mib = _metric(row[6], 24576)
            if total_mib is not None and used_mib is not None and used_mib > total_mib:
                raise ValueError
            gpus.append(
                {
                    "index": index,
                    "uuid": row[1],
                    "model": row[2] or None,
                    "driver_version": row[7] or None,
                    "utilization_percent": utilization,
                    "temperature_celsius": temperature,
                    "memory_total_bytes": int(total_mib * 1024 * 1024)
                    if total_mib is not None
                    else None,
                    "memory_used_bytes": int(used_mib * 1024 * 1024)
                    if used_mib is not None
                    else None,
                    "health": "UNKNOWN" if utilization is None or temperature is None else "OK",
                    "reason_code": "unsupported_metric"
                    if utilization is None or temperature is None
                    else None,
                }
            )
        if len({gpu["index"] for gpu in gpus}) != len(gpus) or len(
            {gpu["uuid"] for gpu in gpus}
        ) != len(gpus):
            raise ValueError
        gpus.sort(key=lambda gpu: int(gpu["index"]))
        unknown = any(gpu["health"] == "UNKNOWN" for gpu in gpus)
        return {
            "gpu_health": {
                "state": "UNKNOWN" if unknown else "OK",
                "reason_code": "unsupported_metric" if unknown else None,
                "inventory_reliable": True,
            },
            "gpus": gpus,
        }
    except (UnicodeDecodeError, ValueError, csv.Error):
        return failed("malformed_output")


class GPUCollector:
    def __init__(
        self,
        path: str,
        *,
        enabled: bool = True,
        timeout: float = 5,
        process: BoundedProcess | None = None,
    ) -> None:
        self.path = path
        self.enabled = enabled
        self.timeout = timeout
        self.process = process or BoundedProcess()

    async def collect(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "gpu_health": {
                    "state": "UNKNOWN",
                    "reason_code": "disabled",
                    "inventory_reliable": False,
                },
                "gpus": [],
            }
        result = await self.process.run([self.path, QUERY, FORMAT], self.timeout)
        if result.reason:
            return failed(result.reason)
        return parse_gpu_output(result.output)
