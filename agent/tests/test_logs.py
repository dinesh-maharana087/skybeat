import asyncio
import json
from dataclasses import replace

import httpx

from skybeat_agent.collectors.logs import JournalCollector, parse_journal
from skybeat_agent.collectors.process import ProcessResult
from skybeat_agent.config import Config
from skybeat_agent.log_watch import LogSender, LogWatchPublisher
from skybeat_agent.runtime import run


def _row(cursor="cursor-1", message="hello", timestamp="1760000000000000", priority="4"):
    return (
        json.dumps(
            {
                "__CURSOR": cursor,
                "MESSAGE": message,
                "__REALTIME_TIMESTAMP": timestamp,
                "PRIORITY": priority,
            }
        ).encode()
        + b"\n"
    )


def _config():
    return Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )


def test_journal_normalizes_only_bounded_safe_records_with_stable_ids():
    raw = _row(message="hello\x1b[31m<script>\n") + _row(
        cursor="cursor-2", timestamp="bad", priority=""
    )
    entries = parse_journal(raw)
    assert len(entries) == 2
    assert entries[0]["message"] == "hello<script>"
    assert entries[0]["severity"] == "warning"
    assert entries[0]["entry_id"] == parse_journal(raw)[0]["entry_id"]
    assert entries[1]["occurred_at"] is None
    assert entries[1]["severity"] is None
    assert len(parse_journal(b"".join(_row(cursor=str(i)) for i in range(100)))) == 80
    assert parse_journal(b"not-json\n" + _row()) == parse_journal(_row())


def test_journal_neutralizes_invalid_unicode_without_stopping_later_records():
    entries = parse_journal(
        _row(cursor="bad\ud800", message="skip") + _row(cursor="good", message="valid\ud800text")
    )
    assert len(entries) == 1
    assert entries[0]["message"] == "valid?text"


def test_collector_uses_only_fixed_journal_queries_and_isolates_failures():
    class Process:
        def __init__(self):
            self.commands = []

        async def run(self, args, timeout):
            self.commands.append((args, timeout))
            if "--dmesg" in args:
                return ProcessResult(b"", b"permission denied", 1, "nonzero_exit")
            return ProcessResult(_row(), b"", 0)

        async def close(self):
            pass

    process = Process()
    collector = JournalCollector(process)

    async def exercise():
        return [
            await collector.collect(source)
            for source in ("skybeat_agent", "system_journal", "kernel")
        ]

    results = asyncio.run(exercise())
    assert [result["status"] for result in results] == [
        "available",
        "available",
        "permission_unavailable",
    ]
    assert all(
        command[:6]
        == [
            "/usr/bin/journalctl",
            "--system",
            "--no-pager",
            "--output=json",
            "--since=-5min",
            "--lines=100",
        ]
        for command, _ in process.commands
    )
    assert "--unit=skybeat-agent.service" in process.commands[0][0]
    assert "--dmesg" in process.commands[2][0]
    assert all(timeout == 4 for _, timeout in process.commands)


def test_log_transport_is_bounded_and_does_not_replay_an_unlimited_queue():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"accepted": 1})

    async def exercise():
        sender = LogSender(_config(), transport=httpx.MockTransport(handle))
        return await sender.send(
            {
                "schema_version": 1,
                "source": "kernel",
                "status": "available",
                "entries": [
                    {"entry_id": "a" * 64, "message": "safe", "occurred_at": None, "severity": None}
                ],
            }
        )

    assert asyncio.run(exercise()) is True
    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert len(requests[0].content) <= 72 * 1024
    assert requests[0].headers["authorization"].startswith("Bearer sb1.")
    assert requests[0].url.path == "/api/v1/agent/logs"


def test_failed_source_does_not_prevent_later_source_upload():
    class Collector:
        async def collect(self, source):
            if source == "skybeat_agent":
                raise PermissionError
            return {"schema_version": 1, "source": source, "status": "available", "entries": []}

    class Sender:
        def __init__(self):
            self.sources = []

        async def send(self, payload):
            self.sources.append(payload["source"])
            return True

    sender = Sender()
    asyncio.run(LogWatchPublisher(Collector(), sender).run_once())
    assert sender.sources == ["system_journal", "kernel"]


def test_missing_journal_and_output_limit_report_errors_without_entries():
    class Process:
        async def run(self, args, timeout):
            return ProcessResult(
                b"partial", b"", None, "command_missing" if "--dmesg" in args else "output_limit"
            )

        async def close(self):
            pass

    async def exercise():
        collector = JournalCollector(Process())
        return await collector.collect("kernel"), await collector.collect("system_journal")

    missing, overflow = asyncio.run(exercise())
    assert missing["status"] == overflow["status"] == "collection_error"
    assert missing["entries"] == overflow["entries"] == []


def test_slow_log_cycle_does_not_delay_heartbeats_and_is_cancelled_on_stop():
    async def exercise():
        stop = asyncio.Event()
        sent = 0
        cancelled = False

        class Sender:
            async def send(self, snapshot):
                nonlocal sent
                sent += 1
                if sent == 2:
                    stop.set()
                return True

        async def system(_):
            return {
                "hostname": "test",
                "ip_addresses": [],
                "os": {},
                "uptime_seconds": None,
                "cpu": {},
                "memory": {},
                "disks": [],
            }

        async def gpu():
            return {
                "gpu_health": {
                    "state": "UNKNOWN",
                    "reason_code": "disabled",
                    "inventory_reliable": False,
                },
                "gpus": [],
            }

        async def slow_logs():
            nonlocal cancelled
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled = True
                raise

        await asyncio.wait_for(
            run(
                replace(_config(), interval=1),
                Sender(),
                system=system,
                gpu=gpu,
                stop=stop,
                jitter=lambda *_: 0,
                log_watch=slow_logs,
            ),
            timeout=2,
        )
        return sent, cancelled

    assert asyncio.run(exercise()) == (2, True)
