from types import SimpleNamespace

from skybeat_agent.collectors import system


def test_system_collection_uses_primed_cpu_and_linux_os_semantics(monkeypatch):
    cpu_calls = []

    def cpu_percent(interval):
        cpu_calls.append(interval)
        return 12.5

    monkeypatch.setattr(system.psutil, "cpu_percent", cpu_percent)
    monkeypatch.setattr(system.psutil, "net_if_addrs", lambda: {})
    monkeypatch.setattr(
        system.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=10, used=4, available=6, percent=40.0),
    )
    monkeypatch.setattr(system.psutil, "boot_time", lambda: 1.0)
    monkeypatch.setattr(system.socket, "gethostname", lambda: "edge")
    monkeypatch.setattr(
        system.platform,
        "freedesktop_os_release",
        lambda: {"NAME": "Ubuntu", "VERSION_ID": "24.04"},
    )
    monkeypatch.setattr(system.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(system.platform, "machine", lambda: "x86_64")

    system.prime_cpu_sample()
    result = system.collect_system(())

    assert cpu_calls == [None, None]
    assert result["cpu"]["utilization_percent"] == 12.5
    assert result["os"] == {
        "name": "Ubuntu",
        "version": "24.04",
        "kernel": "6.8.0",
        "architecture": "x86_64",
    }


def test_system_collection_bounds_ips_and_keeps_failed_mount_metrics_null(monkeypatch):
    addresses = [SimpleNamespace(address=f"192.0.2.{index}") for index in range(20)]
    addresses.append(SimpleNamespace(address="127.0.0.1"))
    monkeypatch.setattr(system.psutil, "net_if_addrs", lambda: {"eth0": addresses})
    monkeypatch.setattr(system.psutil, "disk_usage", lambda mount: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(system.psutil, "virtual_memory", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(system.psutil, "boot_time", lambda: 1.0)
    monkeypatch.setattr(system.psutil, "cpu_percent", lambda interval: 0.0)

    result = system.collect_system(("/",))

    assert len(result["ip_addresses"]) == 16
    assert "127.0.0.1" not in result["ip_addresses"]
    assert result["memory"]["total_bytes"] is None
    assert result["disks"][0]["total_bytes"] is None
