import logging
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.redirects import safe_return_path
from app.dashboard.service import DashboardUser
from app.main import create_app

STATIC_ROOT = Path(__file__).resolve().parents[1] / "app" / "static"
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "app" / "templates"


def dashboard_script() -> str:
    return (STATIC_ROOT / "dashboard.js").read_text(encoding="utf-8")


def dashboard_template() -> str:
    return (TEMPLATE_ROOT / "dashboard.html").read_text(encoding="utf-8")


def dashboard_styles() -> str:
    return (STATIC_ROOT / "dashboard.css").read_text(encoding="utf-8")


def dashboard_shell_styles() -> str:
    return (STATIC_ROOT / "dashboard-shell.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("role_name", ["USER", "ADMIN", "OWNER"])
def test_device_detail_page_requires_auth_and_resolves_canonical_device(role_name):
    from app.dashboard.read import DashboardNotFound
    from app.users.service import UserRole

    device_id = "123e4567-e89b-42d3-a456-426614174000"

    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google", "viewer@example.test", None, 1, UserRole(role_name))

    class ReadService:
        def get_device(self, requested):
            if requested != device_id:
                raise DashboardNotFound("Device not found.")
            return {
                "device_id": device_id,
                "name": "Device <alpha>",
                "project": {"name": "Ops & Dev"},
                "state": "OFFLINE",
                "hostname": "host-a",
                "os": {"name": "Ubuntu", "version": "24.04"},
                "gpu_health": {"effective": "DRIVER_ERROR"},
                "last_seen_at": "2026-10-05T10:00:00Z",
                "latest_received_at": "2026-10-05T10:00:00Z",
                "telemetry_stale": True,
            }

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_read_service = ReadService()
    with TestClient(app, base_url="https://testserver") as client:
        anonymous = client.get(f"/dashboard/devices/{device_id}", follow_redirects=False)
        app.state.dashboard_auth_service = Authenticated()
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        page = client.get(f"/dashboard/devices/{device_id}")
        missing = client.get("/dashboard/devices/123e4567-e89b-42d3-a456-426614174001")
        malformed = client.get("/dashboard/devices/not-a-uuid")

    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == f"/login?next=/dashboard/devices/{device_id}"
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["content-security-policy"]
    assert 'data-dashboard-view="device_detail"' in page.text
    assert 'data-device-id="123e4567-e89b-42d3-a456-426614174000"' in page.text
    assert "Device &lt;alpha&gt;" in page.text
    assert "Ops &amp; Dev" in page.text
    assert "Log Watch" in page.text and "Analyze" in page.text
    assert page.text.count('class="device-agent-lifecycle"') == 1
    assert page.text.count('id="device-agent-lifecycle-heading"') == 1
    assert page.text.count('id="agent-lifecycle-status"') == 1
    assert page.text.count('id="agent-lifecycle-facts"') == 1
    assert page.text.count('id="agent-lifecycle-upgrade"') == (role_name != "USER")
    assert page.text.count('id="agent-lifecycle-rollback"') == (role_name != "USER")
    if role_name != "USER":
        assert (
            'id="agent-lifecycle-upgrade" type="button" class="sb-button--primary" hidden disabled'
            in page.text
        )
        assert (
            'id="agent-lifecycle-rollback" type="button" '
            'class="sb-button--secondary" hidden disabled' in page.text
        )
    assert 'href="/dashboard/devices"' in page.text
    assert missing.status_code == malformed.status_code == 404


def test_device_detail_foundation_uses_canonical_refresh_and_accessible_tabs():
    template = dashboard_template()
    script = dashboard_script()
    assert 'role="tablist"' in template
    assert 'role="tab"' in template
    assert 'role="tabpanel"' in template
    assert "No log reports received yet" in template
    assert 'id="log-watch-sources"' in template
    assert "requestDeviceDetail(deviceId" in script
    assert 'dashboardView === "device_detail"' in script
    assert "function refreshDeviceDetailPage" in script
    assert "deviceAttention(device)" in script
    assert 'href="/dashboard/devices/"' not in template  # UUID is bound only to the selected device


@pytest.mark.parametrize(
    ("state", "gpu_state", "received", "attention"),
    [
        ("ONLINE", "OK", True, "No current attention"),
        ("SUSPECT", "OK", True, "SUSPECT"),
        ("OFFLINE", "DRIVER_ERROR", True, "DRIVER ERROR"),
        ("AWAITING_FIRST_HEARTBEAT", "UNKNOWN", False, "Awaiting telemetry"),
    ],
)
def test_device_detail_renders_canonical_states_and_escapes_reported_identity(
    state, gpu_state, received, attention
):
    from app.users.service import UserRole

    device_id = "123e4567-e89b-42d3-a456-426614174000"

    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google", "viewer@example.test", None, 1, UserRole.USER)

    class ReadService:
        def get_device(self, requested):
            return {
                "device_id": device_id,
                "name": "Device <script>alert(1)</script>",
                "project": {"name": "Ops & <Dev>"},
                "hostname": "host<script>",
                "state": state,
                "os": {"name": "Ubuntu <img>", "version": "24.04", "kernel": "kernel<bad>"}
                if received
                else {},
                "gpu_health": {"effective": gpu_state, "reported": None},
                "last_seen_at": "2026-10-05T10:00:00Z" if received else None,
                "latest_received_at": "2026-10-05T10:00:00Z" if received else None,
                "telemetry_stale": state in {"SUSPECT", "OFFLINE"} and received,
                "device_token": "should-never-render",
            }

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    app.state.dashboard_read_service = ReadService()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        page = client.get(f"/dashboard/devices/{device_id}")

    assert page.status_code == 200
    assert state in page.text and gpu_state in page.text
    assert attention in page.text
    assert "Device &lt;script&gt;" in page.text
    assert "Ops &amp; &lt;Dev&gt;" in page.text
    assert "host&lt;script&gt;" in page.text
    assert "<script>alert(1)</script>" not in page.text
    assert "should-never-render" not in page.text
    if received:
        assert "Ubuntu &lt;img&gt; 24.04" in page.text
        assert "kernel&lt;bad&gt;" in page.text
    else:
        assert "Not reported" in page.text
        assert "Awaiting first heartbeat" in page.text


def test_device_detail_tabs_and_refresh_interaction_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = script.split("async function refreshDeviceDetailPage() {", 1)[1].split(
        "\nfunction detailPairs(", 1
    )[0]
    controller = "async function refreshDeviceDetailPage() {" + controller
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const nodes = new Map();
        for (const id of ["device-tab-log-watch", "device-tab-analyze",
                          "device-panel-log-watch", "device-panel-analyze", "device-page-status"]) {
          nodes.set(id, { id, hidden: id === "device-panel-analyze", attributes: {}, handlers: {},
            setAttribute(key, value) { this.attributes[key] = value; },
            getAttribute(key) { return this.attributes[key]; },
            addEventListener(key, handler) { this.handlers[key] = handler; },
            focus() { this.focused = true; } });
        }
        globalThis.document = { getElementById: (id) => nodes.get(id), hidden: false };
        globalThis.deviceDetailPage = { dataset: { deviceId: "test-device" } };
        globalThis.lastLogAttemptAt = Date.now();
        globalThis.refreshing = false;
        let resolveRequest;
        let requestCount = 0;
        let renderCount = 0;
        let scheduleCount = 0;
        let staleCount = 0;
        let freshCount = 0;
        let fail = false;
        globalThis.requestDeviceDetail = () => {
          requestCount += 1;
          if (fail) return Promise.reject(new Error("network"));
          return new Promise((resolve) => { resolveRequest = resolve; });
        };
        globalThis.renderDeviceDetailPage = () => { renderCount += 1; };
        globalThis.scheduleRefresh = () => { scheduleCount += 1; };
        globalThis.markDashboardStale = () => { staleCount += 1; };
        globalThis.markDashboardFresh = () => { freshCount += 1; };
        globalThis.refreshAgentLifecycle = () => Promise.resolve();
        vm.runInThisContext(readFileSync(0, "utf8"));

        const log = nodes.get("device-tab-log-watch");
        const analyze = nodes.get("device-tab-analyze");
        analyze.setAttribute("aria-controls", "device-panel-analyze");
        log.setAttribute("aria-controls", "device-panel-log-watch");
        initializeDeviceDetailTabs();
        log.handlers.keydown({ key: "ArrowRight", preventDefault() {} });
        if (analyze.attributes["aria-selected"] !== "true" ||
            nodes.get("device-panel-analyze").hidden || !analyze.focused) {
          throw new Error("ArrowRight did not select and focus Analyze");
        }
        log.handlers.click();
        if (log.attributes["aria-selected"] !== "true" ||
            !nodes.get("device-panel-analyze").hidden) {
          throw new Error("click did not restore Log Watch");
        }
        const first = refreshDeviceDetailPage();
        await refreshDeviceDetailPage();
        if (requestCount !== 1) throw new Error("overlapping refresh started");
        resolveRequest({ server_time: "2026-10-05T10:00:00Z" });
        await first;
        fail = true;
        await refreshDeviceDetailPage();
        if (renderCount !== 1 || freshCount !== 1 || staleCount !== 1 ||
            scheduleCount !== 2 ||
            !nodes.get("device-page-status").textContent.includes("retained")) {
          throw new Error("failed refresh did not retain last successful state");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_agent_lifecycle_rendering_and_failed_refresh_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = script.split("function lifecycleActionEligible(action) {", 1)[1].split(
        "\nfunction logWindowForRange(", 1
    )[0]
    controller = "function lifecycleActionEligible(action) {" + controller
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        globalThis.lifecycleGeneration = 0;
        globalThis.lifecycleState = null;
        globalThis.lifecycleAvailable = false;
        globalThis.lifecycleSubmitting = false;
        globalThis.deviceDetailPage = { dataset: { deviceId: "device-1" } };
        globalThis.lifecycleStatus = { textContent: "Loading agent release state…" };
        globalThis.lifecycleFacts = { facts: [["Reported version", "Loading…"]] };
        globalThis.lifecycleUpgrade = { hidden: true, disabled: true };
        globalThis.lifecycleRollback = { hidden: true, disabled: true };
        globalThis.canManage = true;
        globalThis.detailPairs = (element, facts) => { element.facts = facts; };
        globalThis.window = { confirm: () => true };
        let mutations = 0;
        let rejectMutation;
        globalThis.requestDashboardMutation = async () => {
          mutations += 1;
          return new Promise((_, reject) => { rejectMutation = reject; });
        };
        const responses = [];
        globalThis.fetch = async () => {
          const next = responses.shift();
          if (next instanceof Error) throw next;
          if (next === 503) return { ok: false, status: 503 };
          return { ok: true, json: async () => next };
        };
        vm.runInThisContext(readFileSync(0, "utf8"));
        const version = () => lifecycleFacts.facts.find(([name]) => name === "Reported version")[1];
        const denied = () => lifecycleUpgrade.hidden && lifecycleUpgrade.disabled &&
          lifecycleRollback.hidden && lifecycleRollback.disabled;
        responses.push(503);
        await refreshAgentLifecycle();
        if (!lifecycleStatus.textContent.includes("unavailable") ||
            version() !== "Unavailable" || !denied()) {
          throw new Error("first failed read left loading facts or enabled controls");
        }
        responses.push({ installed_version: null, latest_approved_version: "1.0.5",
          compatibility: "UNKNOWN", operation: null,
          actions: { upgrade: false, rollback: false } });
        await refreshAgentLifecycle();
        if (version() !== "Unknown (legacy agent)" ||
            !lifecycleStatus.textContent.includes("unknown") || !denied()) {
          throw new Error("unknown legacy version was not rendered separately");
        }
        responses.push({ installed_version: "1.0.0", latest_approved_version: "1.0.5",
          compatibility: "BOOTSTRAP_REQUIRED", operation: null,
          actions: { upgrade: false, rollback: false } });
        await refreshAgentLifecycle();
        if (version() !== "Unknown (legacy agent)" ||
            !lifecycleStatus.textContent.includes("unsupported") || !denied()) {
          throw new Error("unreliable legacy report was presented as an installed version");
        }
        responses.push({ installed_version: "1.0.4", latest_approved_version: "1.0.5",
          compatibility: "UPGRADE_AVAILABLE", operation: null,
          actions: { upgrade: true, rollback: false } });
        await refreshAgentLifecycle();
        if (version() !== "1.0.4" || lifecycleUpgrade.hidden ||
            lifecycleUpgrade.disabled || !lifecycleRollback.disabled) {
          throw new Error("eligible upgrade was not rendered");
        }
        responses.push(new Error("network"));
        await refreshAgentLifecycle();
        if (version() !== "1.0.4" ||
            !lifecycleStatus.textContent.includes("retained") || !denied()) {
          throw new Error("failed refresh erased verified facts or retained action eligibility");
        }
        await submitAgentLifecycle("upgrade");
        if (mutations !== 0) throw new Error("stale action was submitted");
        responses.push({ installed_version: "1.0.5", latest_approved_version: "1.0.5",
          compatibility: "CURRENT", operation: { action: "UPGRADE", state: "SUCCEEDED",
            previous_version: "1.0.4", rollback_available: true },
          actions: { upgrade: false, rollback: true } });
        await refreshAgentLifecycle();
        if (lifecycleRollback.hidden || lifecycleRollback.disabled || !lifecycleUpgrade.disabled) {
          throw new Error("eligible rollback was not rendered");
        }
        const submitted = submitAgentLifecycle("rollback");
        responses.push({ installed_version: "1.0.5", latest_approved_version: "1.0.5",
          compatibility: "CURRENT", operation: { action: "UPGRADE", state: "SUCCEEDED",
            previous_version: "1.0.4", rollback_available: true },
          actions: { upgrade: false, rollback: true } });
        await refreshAgentLifecycle();
        if (!denied()) throw new Error("poll enabled controls during a pending request");
        rejectMutation(new Error("request rejected"));
        await submitted;
        if (mutations !== 1 || !denied()) {
          throw new Error("rejected lifecycle request re-enabled stale controls");
        }
        responses.push({ installed_version: "1.0.4", latest_approved_version: "1.0.5",
          compatibility: "UPGRADE_AVAILABLE", operation: null });
        await refreshAgentLifecycle();
        if (!denied()) throw new Error("missing server eligibility enabled an action");
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_log_watch_uses_existing_detail_refresh_and_text_only_source_cards():
    template = dashboard_template()
    script = dashboard_script()
    css = dashboard_shell_styles()
    assert 'id="device-panel-log-watch"' in template
    assert 'id="log-watch-offline"' in template
    assert 'id="log-watch-sources"' in template
    assert "Device offline. Stored recent logs remain available" in template
    for source in ("skybeat_agent", "system_journal", "kernel"):
        assert source in script
    assert "void loadDeviceLogs({ auto: true })" in script
    assert "if (refreshing) return;" in script
    assert "Last successful logs are retained" in script
    assert 'element("p", entry.message)' in script
    assert "innerHTML" not in script
    assert "overflow-wrap: anywhere" in css


def test_log_watch_rendering_preserves_untrusted_message_as_text_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function updateLogWatchOffline() {"
        + script.split("function updateLogWatchOffline() {", 1)[1].split(
            "\nasync function loadDeviceLogs(", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        function node(tag, text = "") {
          return { tag, textContent: text, children: [],
            append(...children) { this.children.push(...children); },
            replaceChildren(...children) { this.children = children; } };
        }
        const nodes = new Map(["log-watch-sources", "log-watch-results", "log-watch-status",
          "log-watch-summary", "log-watch-offline", "log-watch-older", "log-watch-refresh"]
          .map((id) => [id, node("div")]));
        globalThis.document = { getElementById: (id) => nodes.get(id),
          createElement: (tag) => node(tag) };
        globalThis.element = node;
        globalThis.LOG_SOURCE_LABELS = { skybeat_agent: "SkyBeat Agent", system_journal: "System",
          kernel: "Kernel" };
        globalThis.logWatchState = { items: [], sources: [], nextCursor: null, loading: false,
          offline: false };
        vm.runInThisContext(readFileSync(0, "utf8"));
        renderDeviceLogs({ sources: [
          { source: "skybeat_agent", status: "available" },
          { source: "system_journal", status: "permission_unavailable" },
          { source: "kernel", status: "no_report" },
        ], items: [{ id: 1, source: "skybeat_agent", message: "<img src=x onerror=alert(1)>",
                     severity: "warning", received_at: "2026-10-06T00:00:00Z" }] });
        const container = nodes.get("log-watch-sources");
        if (container.children.length !== 3) throw new Error("missing source card");
        const message = nodes.get("log-watch-results").children[0].children[1];
        if (message.textContent !== "<img src=x onerror=alert(1)>" ||
            message.children.length !== 0) throw new Error("log message was not text only");
        if (container.children[1].children[1].textContent !== "Permission unavailable") {
          throw new Error("permission state was hidden");
        }
        if (!container.children[0].children[1].className.includes("state--available") ||
            !container.children[1].children[1].className.includes(
              "state--permission-unavailable") ||
            !container.children[2].children[1].className.includes("state--no-report")) {
          throw new Error("source state styling was lost");
        }
        renderDeviceLogs({ items: [{ id: 1, source: "skybeat_agent", message: "duplicate",
          received_at: "2026-10-06T00:00:00Z" }], next_cursor: null }, true);
        if (nodes.get("log-watch-results").children.length !== 1) {
          throw new Error("overlapping page duplicated a log");
        }
        logWatchState.offline = true;
        updateLogWatchOffline();
        if (nodes.get("log-watch-offline").hidden ||
            nodes.get("log-watch-results").children.length !== 1) {
          throw new Error("offline state hid stored history");
        }
        renderDeviceLogs({ sources: [
          { source: "skybeat_agent", status: "no_report" },
          { source: "system_journal", status: "no_report" },
          { source: "kernel", status: "no_report" },
        ], items: [] });
        if (!nodes.get("log-watch-summary").textContent.includes("collected yet")) {
          throw new Error("never-collected state is unclear");
        }
        renderDeviceLogs({ sources: [{ source: "kernel", status: "available" }], items: [] });
        if (!nodes.get("log-watch-summary").textContent.includes("match these filters")) {
          throw new Error("no-match state is unclear");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_log_watch_query_uses_utc_window_literal_search_and_bounded_cursor_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function logWindowForRange("
        + script.split("function logWindowForRange(", 1)[1].split(
            "\nasync function requestDeviceLogs(", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        globalThis.LOG_RANGE_MS = { "1h": 3600000, "24h": 86400000 };
        globalThis.LOG_PAGE_LIMIT = 60;
        vm.runInThisContext(readFileSync(0, "utf8"));
        const window = logWindowForRange("1h", Date.UTC(2026, 9, 9, 12, 0, 0));
        if (window.from !== "2026-10-09T11:00:00.000Z" ||
            window.until !== "2026-10-09T12:00:00.000Z") {
          throw new Error("time range is not a fixed UTC window");
        }
        const query = logQueryParams({ source: "kernel", q: "GPU 50%_", window }, "opaque");
        if (query.get("source") !== "kernel" || query.get("q") !== "GPU 50%_" ||
            query.get("cursor") !== "opaque" || query.get("limit") !== "60" ||
            query.get("from") !== window.from || query.get("until") !== window.until ||
            query.has("time_basis")) {
          throw new Error("filter or cursor was lost");
        }
        const incident = logQueryParams({ source: "kernel", q: "GPU 50%_", window,
          timeBasis: "occurred" }, "incident-cursor");
        if (incident.get("time_basis") !== "occurred" ||
            incident.get("cursor") !== "incident-cursor" ||
            incident.get("from") !== window.from || incident.get("until") !== window.until) {
          throw new Error("incident occurrence basis or cursor was lost");
        }
        if (normalizeLogSearch("  GPU   50%_  ") !== "GPU 50%_") {
          throw new Error("search was not trimmed");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_log_watch_discards_stale_filter_response_and_keeps_fixed_cursor_window_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "async function loadDeviceLogs("
        + script.split("async function loadDeviceLogs(", 1)[1].split(
            "\nfunction initializeLogWatch()", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const nodes = new Map(["log-watch-status", "log-watch-older", "log-watch-refresh"]
          .map((id) => [id, { textContent: "", disabled: false, hidden: false }]));
        globalThis.document = { getElementById: (id) => nodes.get(id) };
        globalThis.deviceDetailPage = { dataset: { deviceId: "device-a" } };
        globalThis.lastLogAttemptAt = 0;
        globalThis.logWatchState = { source: "", range: "24h", q: "", window: null,
          items: [], sources: [], nextCursor: null, hasSuccess: false, olderLoaded: false,
          generation: 0, controller: null, loading: false };
        const calls = [];
        const renders = [];
        globalThis.logWindowForRange = () => ({ from: "fixed-from", until: "fixed-until" });
        globalThis.requestDeviceLogs = (_id, filters, cursor, signal) =>
          new Promise((resolve, reject) => calls.push({
            filters, cursor, signal, resolve, reject,
          }));
        globalThis.renderDeviceLogs = (payload, older) => {
          renders.push([payload.name, older]);
          logWatchState.nextCursor = payload.next_cursor;
          logWatchState.hasSuccess = true;
        };
        globalThis.syncLogWatchButtons = () => {};
        vm.runInThisContext(readFileSync(0, "utf8"));
        const stale = loadDeviceLogs();
        logWatchState.source = "kernel";
        logWatchState.q = "GPU";
        const current = loadDeviceLogs();
        if (!calls[0].signal.aborted || calls[1].filters.source !== "kernel" ||
            calls[1].filters.q !== "GPU") {
          throw new Error("filter change did not supersede request");
        }
        calls[1].resolve({ name: "new", next_cursor: "page-two" });
        await current;
        calls[0].resolve({ name: "stale", next_cursor: null });
        await stale;
        if (JSON.stringify(renders) !== JSON.stringify([["new", false]])) {
          throw new Error("stale response replaced current results");
        }
        const older = loadDeviceLogs({ older: true });
        if (calls[2].cursor !== "page-two" ||
            calls[2].filters.window !== calls[1].filters.window) {
          throw new Error("older page lost its cursor or fixed window");
        }
        calls[2].resolve({ name: "older", next_cursor: null });
        await older;
        if (JSON.stringify(renders) !== JSON.stringify([["new", false], ["older", true]])) {
          throw new Error("older results were not appended");
        }
        const failed = loadDeviceLogs();
        calls[3].reject(new Error("network"));
        await failed;
        if (renders.length !== 2 ||
            !nodes.get("log-watch-status").textContent.includes("retained")) {
          throw new Error("failed refresh cleared successful logs");
        }
        logWatchState.contextWindow = { from: "incident-from", until: "incident-until" };
        const incident = loadDeviceLogs();
        if (calls[4].filters.timeBasis !== "occurred" ||
            calls[4].filters.window !== logWatchState.contextWindow) {
          throw new Error("incident window was not queried by occurrence time");
        }
        calls[4].resolve({ name: "incident", next_cursor: "incident-next" });
        await incident;
        const incidentOlder = loadDeviceLogs({ older: true });
        if (calls[5].filters.timeBasis !== "occurred" ||
            calls[5].filters.window !== calls[4].filters.window ||
            calls[5].cursor !== "incident-next") {
          throw new Error("incident paging lost its time basis or window");
        }
        calls[5].resolve({ name: "incident-older", next_cursor: null });
        await incidentOlder;
        logWatchState.contextWindow = null;
        const ordinary = loadDeviceLogs();
        if (calls[6].filters.timeBasis !== "received") {
          throw new Error("normal Log Watch did not restore receipt time");
        }
        calls[6].resolve({ name: "ordinary", next_cursor: null });
        await ordinary;
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_log_watch_controls_query_selected_filters_and_reset_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function initializeLogWatch() {"
        + script.split("function initializeLogWatch() {", 1)[1].split(
            "\nasync function refreshDeviceDetailPage()", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const nodes = new Map(["log-watch-source", "log-watch-range", "log-watch-search",
          "log-watch-search-form", "log-watch-reset", "log-watch-refresh", "log-watch-older"]
          .map((id) => [id, { value: "", options: [], handlers: {},
            append(option) { this.options.push(option); },
            querySelector() { return null; },
            addEventListener(name, callback) { this.handlers[name] = callback; } }]));
        globalThis.document = { getElementById: (id) => nodes.get(id) };
        globalThis.Option = function(label, value) { this.label = label; this.value = value; };
        globalThis.LOG_SOURCE_LABELS = { skybeat_agent: "SkyBeat Agent", system_journal: "System",
          kernel: "Kernel" };
        globalThis.logWatchState = { source: "", range: "24h", q: "" };
        globalThis.normalizeLogSearch = (value) => value.trim().replace(/\\s+/g, " ");
        const requests = [];
        globalThis.loadDeviceLogs = (options = {}) => {
          requests.push({ source: logWatchState.source, range: logWatchState.range,
            q: logWatchState.q, options });
        };
        vm.runInThisContext(readFileSync(0, "utf8"));
        initializeLogWatch();
        const source = nodes.get("log-watch-source");
        if (source.options.map((option) => option.value).join(",") !==
            "skybeat_agent,system_journal,kernel") {
          throw new Error("canonical source options missing");
        }
        source.value = "kernel";
        source.handlers.change();
        nodes.get("log-watch-range").value = "1h";
        nodes.get("log-watch-range").handlers.change();
        nodes.get("log-watch-search").value = "  GPU   error  ";
        if (requests.length !== 2) throw new Error("search queried on keystroke");
        nodes.get("log-watch-search-form").handlers.submit({ preventDefault() {} });
        if (requests.length !== 3 || requests[2].source !== "kernel" ||
            requests[2].range !== "1h" || requests[2].q !== "GPU error") {
          throw new Error("search/filter state was not queried");
        }
        nodes.get("log-watch-reset").handlers.click();
        if (requests.length !== 4 || requests[3].source !== "" ||
            requests[3].range !== "24h" || requests[3].q !== "") {
          throw new Error("reset did not restore default filters");
        }
        nodes.get("log-watch-older").handlers.click();
        if (!requests[4].options.older) throw new Error("Load older was not wired");
        nodes.get("log-watch-refresh").handlers.click();
        if (requests.length !== 6) throw new Error("manual refresh was not wired");
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_incident_diagnostics_preview_is_text_only_and_distinguishes_empty_results_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function renderIncidentDiagnostics(payload) {"
        + script.split("function renderIncidentDiagnostics(payload) {", 1)[1].split(
            "\nasync function loadIncidentDiagnostics(", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        function node(tag, value = "") {
          return { tag, textContent: value, children: [], hidden: true,
            get childElementCount() { return this.children.length; },
            append(...children) { this.children.push(...children); },
            replaceChildren(...children) { this.children = children; } };
        }
        const nodes = new Map(["incident-diagnostics-context", "incident-diagnostics-results",
          "incident-diagnostics-result-status", "incident-open-log-watch"]
          .map((id) => [id, node("div")]));
        globalThis.document = { getElementById: (id) => nodes.get(id), createElement: node };
        globalThis.element = node;
        globalThis.LOG_SOURCE_LABELS = { kernel: "Kernel" };
        globalThis.incidentDiagnosticsState = { payload: null };
        vm.runInThisContext(readFileSync(0, "utf8"));
        const payload = { incident: { type: "GPU", point: "opened",
          anchor_at: "2026-10-12T12:00:00Z" }, truncated: true,
          diagnostics: [{ source: "kernel", severity: "warning",
            occurred_at: "2026-10-12T11:59:00Z",
            received_at: "2026-10-12T12:20:00Z", message: "<img src=x onerror=alert(1)>" }] };
        renderIncidentDiagnostics(payload);
        const metadata = nodes.get("incident-diagnostics-results").children[0].children[0];
        if (!metadata.textContent.includes(new Date("2026-10-12T11:59:00Z").toLocaleString()) ||
            metadata.textContent.includes(new Date("2026-10-12T12:20:00Z").toLocaleString()) ||
            !nodes.get("incident-diagnostics-context").textContent.includes("event time")) {
          throw new Error("preview did not display occurrence time");
        }
        const message = nodes.get("incident-diagnostics-results").children[0].children[1];
        if (message.textContent !== "<img src=x onerror=alert(1)>" || message.children.length) {
          throw new Error("diagnostic message was interpreted as HTML");
        }
        if (!nodes.get("incident-diagnostics-result-status").textContent.includes(
            "limited to 50") ||
            nodes.get("incident-open-log-watch").hidden) {
          throw new Error("bounded preview or full Log Watch action is missing");
        }
        renderIncidentDiagnostics({ ...payload, diagnostics: [], truncated: false });
        if (!nodes.get("incident-diagnostics-result-status").textContent.includes(
            "No stored diagnostics were captured around this incident.")) {
          throw new Error("empty correlation state is unclear");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_incident_open_in_log_watch_preserves_server_utc_window_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function openIncidentInLogWatch() {"
        + script.split("function openIncidentInLogWatch() {", 1)[1].split(
            "\nfunction initializeIncidentCorrelation()", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const range = { value: "24h", options: [],
          querySelector() { return this.options[0] ?? null; },
          append(option) { this.options.push(option); } };
        const nodes = new Map(["log-watch-range", "log-watch-source", "log-watch-search",
          "device-tab-log-watch"].map((id) => [id, { value: "old", click() {} }]));
        nodes.set("log-watch-range", range);
        let selected = false;
        nodes.get("device-tab-log-watch").click = () => { selected = true; };
        globalThis.document = { getElementById: (id) => nodes.get(id) };
        globalThis.Option = function(label, value) { this.label = label; this.value = value; };
        globalThis.logWatchState = { source: "kernel", range: "24h", q: "old",
          contextWindow: null };
        globalThis.incidentDiagnosticsState = { payload: {
          window_start: "2026-10-12T11:55:00Z", window_end: "2026-10-12T12:10:00Z" } };
        let loaded = false;
        globalThis.loadDeviceLogs = () => { loaded = true; };
        vm.runInThisContext(readFileSync(0, "utf8"));
        openIncidentInLogWatch();
        if (!selected || !loaded || range.value !== "incident" ||
            logWatchState.contextWindow.from !== "2026-10-12T11:55:00Z" ||
            logWatchState.contextWindow.until !== "2026-10-12T12:10:00Z" ||
            logWatchState.source !== "" || logWatchState.q !== "") {
          throw new Error("incident context was not preserved in Log Watch");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_incident_preview_discards_stale_response_and_distinguishes_fetch_errors_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "async function loadIncidentDiagnostics("
        + script.split("async function loadIncidentDiagnostics(", 1)[1].split(
            "\nfunction openIncidentInLogWatch()", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const nodes = new Map(["incident-diagnostics-preview", "incident-diagnostics-context",
          "incident-diagnostics-results", "incident-diagnostics-result-status",
          "incident-open-log-watch"]
          .map((id) => [id, { textContent: "", hidden: true, replaceChildren() {} }]));
        globalThis.document = { getElementById: (id) => nodes.get(id) };
        globalThis.deviceDetailPage = { dataset: { deviceId: "device-a" } };
        globalThis.incidentDiagnosticsState = { generation: 0, controller: null, payload: null };
        const calls = [];
        const rendered = [];
        globalThis.requestIncidentDiagnostics = (_device, incidentId, point, signal) =>
          new Promise((resolve, reject) => calls.push({
            incidentId, point, signal, resolve, reject,
          }));
        globalThis.renderIncidentDiagnostics = (payload) => rendered.push(payload.id);
        vm.runInThisContext(readFileSync(0, "utf8"));
        const stale = loadIncidentDiagnostics("old", "opened");
        const current = loadIncidentDiagnostics("new", "recovered");
        if (!calls[0].signal.aborted || calls[1].point !== "recovered") {
          throw new Error("new selection did not supersede old request");
        }
        calls[1].resolve({ id: "new" });
        await current;
        calls[0].resolve({ id: "old" });
        await stale;
        if (rendered.join() !== "new") throw new Error("stale preview replaced new preview");
        const failed = loadIncidentDiagnostics("failed", "opened");
        calls[2].reject(Object.assign(new Error("unavailable"), { status: 503 }));
        await failed;
        if (!nodes.get("incident-diagnostics-result-status").textContent.includes(
            "temporarily unavailable")) throw new Error("fetch failure looked like no results");
        const missing = loadIncidentDiagnostics("missing", "opened");
        calls[3].reject(Object.assign(new Error("missing"), { status: 404 }));
        await missing;
        if (!nodes.get("incident-diagnostics-result-status").textContent.includes("not found")) {
          throw new Error("missing incident looked like fetch failure");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_incident_context_link_opens_analyze_with_recovery_point_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable on this host")
    script = dashboard_script()
    controller = (
        "function initializeIncidentCorrelation() {"
        + script.split("function initializeIncidentCorrelation() {", 1)[1].split(
            "\nfunction initializeDeviceDetailTabs()", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        import { readFileSync } from "node:fs";
        import vm from "node:vm";
        const incidentId = "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0";
        const nodes = new Map(["incident-diagnostics-refresh", "incident-open-log-watch",
          "device-tab-analyze"].map((id) => [id, { handlers: {},
            addEventListener(name, callback) { this.handlers[name] = callback; },
            click() { this.clicked = true; } }]));
        globalThis.document = { getElementById: (id) => nodes.get(id) };
        globalThis.window = { location: { search: `?incident=${incidentId}&point=recovered` } };
        globalThis.CANONICAL_UUID = /^[0-9a-f-]{36}$/i;
        let listLoaded = false;
        let selected = null;
        globalThis.loadDevicePageIncidents = () => { listLoaded = true; };
        globalThis.loadIncidentDiagnostics = (id, point) => { selected = [id, point]; };
        globalThis.openIncidentInLogWatch = () => {};
        vm.runInThisContext(readFileSync(0, "utf8"));
        initializeIncidentCorrelation();
        if (!listLoaded || !nodes.get("device-tab-analyze").clicked ||
            selected[0] !== incidentId || selected[1] !== "recovered") {
          throw new Error("incident link lost recovery context");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=controller,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_dashboard_page_redirects_unauthenticated_browser_to_google_login():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/"
    assert "set-cookie" not in response.headers


def test_login_page_is_a_safe_explicit_google_entry_point():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        login = client.get("/login?next=/dashboard/devices")
        theme = client.get("/static/skybeat-theme.css")
        external = client.get("/login?next=https://attacker.example/")
        protected = client.get("/dashboard/devices", follow_redirects=False)

    assert login.status_code == 200
    assert 'href="/auth/google/login?next=/dashboard/devices"' in login.text
    assert "Continue with Google" in login.text
    assert 'class="login-brand-mark"' in login.text
    assert 'href="/static/skybeat-theme.css?v=stage12c-ux6"' in login.text
    assert 'href="/static/skybeat-theme.css?v=stage12c-ux6"' in dashboard_template()
    assert theme.status_code == 200
    assert theme.headers["content-type"].startswith("text/css")
    assert "--sb-color-pulse: #22d3ee" in theme.text
    assert "Powered by Assert AI" in login.text
    assert external.status_code == 200
    assert 'href="/auth/google/login"' in external.text
    assert protected.headers["location"] == "/login?next=/dashboard/devices"


def test_safe_return_path_rejects_external_protocol_relative_and_malformed_targets():
    for target in (
        "https://attacker.example/",
        "http://attacker.example/",
        "//attacker.example/",
        "/\\attacker.example/",
        "javascript:alert(1)",
        "data:text/html,unsafe",
        "/dashboard#fragment",
        "/dashboard with-space",
        "dashboard/devices",
        "/" + "a" * 2049,
    ):
        assert safe_return_path(target) is None

    assert safe_return_path("/dashboard/devices?project=ops") == "/dashboard/devices?project=ops"


def test_all_protected_dashboard_views_preserve_only_their_internal_return_path():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        responses = {
            path: client.get(path, follow_redirects=False)
            for path in (
                "/dashboard",
                "/dashboard/projects",
                "/dashboard/users",
                "/dashboard/notifications",
            )
        }

    assert responses["/dashboard"].headers["location"] == "/login?next=/dashboard"
    assert responses["/dashboard/projects"].headers["location"] == "/login?next=/dashboard/projects"
    assert responses["/dashboard/users"].headers["location"] == "/login?next=/dashboard/users"
    assert (
        responses["/dashboard/notifications"].headers["location"]
        == "/login?next=/dashboard/notifications"
    )


def test_login_page_shows_only_safe_error_copy_and_redirects_authenticated_users():
    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        failed = client.get("/login?error=verification_failed")
        app.state.dashboard_auth_service = Authenticated()
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        authenticated = client.get("/login", follow_redirects=False)

    assert failed.status_code == 200
    assert "Google sign-in could not be verified." in failed.text
    assert "verification_failed" not in failed.text
    assert authenticated.status_code == 303
    assert authenticated.headers["location"] == "/dashboard"


def test_dashboard_logout_returns_users_to_the_login_page_source():
    script = dashboard_script()

    assert 'window.location.assign("/login")' in script
    assert 'window.location.assign("/auth/google/login")' not in script


def test_project_submission_keeps_normal_management_errors_safe_and_actionable():
    script = dashboard_script()

    assert "You no longer have permission to create projects." in script
    assert "A project change conflicts with the current state. Refresh and try again." in script
    assert "Enter a valid project name and try again." in script


def test_authenticated_dashboard_routes_render_selected_view_controls_and_required_dialogs():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        root = client.get("/", follow_redirects=False)
        overview = client.get("/dashboard")
        devices = client.get("/dashboard/devices")
        projects = client.get("/dashboard/projects")

    assert root.status_code == 303
    assert root.headers["location"] == "/dashboard"
    assert 'data-dashboard-view="overview"' in overview.text
    assert 'id="devices"' not in overview.text
    assert 'data-dashboard-view="devices"' in devices.text
    assert 'id="devices"' in devices.text
    assert 'data-dashboard-view="projects"' in projects.text
    assert 'id="new-project"' in projects.text
    assert 'href="/dashboard"' in overview.text
    assert 'href="#overview-heading"' not in overview.text
    assert 'id="sidebar-toggle"' in overview.text
    assert 'id="new-project"' in overview.text
    assert 'id="project-dialog"' in overview.text
    assert 'id="project-dialog"' in devices.text
    assert 'id="project-dialog"' in projects.text
    assert 'id="new-project"' not in devices.text
    assert 'id="new-project-from-enroll"' in devices.text


def test_admin_deployments_page_is_management_only_and_has_to_install_workspace():
    from app.users.service import UserRole

    class Authenticated:
        def __init__(self, role):
            self.role = role

        def authenticate_session(self, token):
            return DashboardUser("google", "ops@example.test", None, 1, self.role)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated(UserRole.ADMIN)
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        allowed = client.get("/dashboard/deployments")
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated(UserRole.USER)
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        denied = client.get("/dashboard/deployments")

    assert allowed.status_code == 200
    assert 'data-dashboard-view="deployments"' in allowed.text
    assert 'id="deployments-list"' in allowed.text
    assert 'id="deployment-delete-dialog"' in allowed.text
    assert 'id="deployment-delete-confirm"' in allowed.text
    assert "No devices waiting for installation." in allowed.text
    assert denied.status_code == 403


def test_deployment_cards_are_minimal_and_use_the_authoritative_pending_state():
    source = dashboard_script()
    styles = dashboard_styles()
    template = dashboard_template()
    deployment_section = source[
        source.index("function deploymentStateLabel") : source.index("function openUserDialog")
    ]

    assert 'PENDING: "READY"' in deployment_section
    assert 'EXPIRED: "TOKEN EXPIRED"' in deployment_section
    assert 'element("button", "Agent Package")' in deployment_section
    assert 'element("button", "Copy Instruction")' in deployment_section
    assert "deploymentDeleteIcon" in deployment_section
    assert (
        'remove.setAttribute("aria-label", `Delete prepared device ${deployment.device_name}`);'
        in deployment_section
    )
    assert 'const isReady = deployment.state === "PENDING";' in deployment_section
    assert "download.disabled = !isReady || deploymentRelease === null;" in deployment_section
    assert (
        "copyInstructions.disabled = !isReady || deploymentRelease === null;" in deployment_section
    )
    assert "GPU monitoring" not in deployment_section
    assert "Minimum expected GPUs" not in deployment_section
    assert "Token expires" not in deployment_section
    assert "Created" not in deployment_section
    assert "Refresh status" not in deployment_section
    assert "Reissue token" not in deployment_section
    assert "transientDeploymentTokens" not in deployment_section
    assert "sbe1." not in deployment_section
    assert '<section class="deployment-workspace"' in template
    assert 'id="deployments-list" class="deployment-grid"' in template
    assert 'card.className = "deployment-card";' in deployment_section
    assert 'heading.className = "deployment-card__header";' in deployment_section
    assert 'actions.className = "deployment-card__actions";' in deployment_section
    assert 'class="deployment-release-status"' in template
    assert ".deployment-workspace .deployment-grid" in styles
    assert "repeat(3,minmax(0,1fr))" in styles
    assert "@media (max-width:1200px){.deployment-workspace .deployment-grid" in styles
    assert "repeat(2,minmax(0,1fr))" in styles
    assert "@media (max-width:720px)" in styles
    assert "grid-template-columns:1fr" in styles
    assert ".deployment-card{" in styles
    assert "min-height:11rem" in styles
    assert ".deployment-card__actions" in styles
    assert ".deployment-card__delete" in styles
    assert ".status-ready" in styles
    assert ".status-token-expired" in styles


def test_dashboard_shell_serves_the_company_logo_on_every_dashboard_view():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        views = [
            client.get(path) for path in ("/dashboard", "/dashboard/devices", "/dashboard/projects")
        ]
        logo = client.get("/static/assert_logo.png")

    assert all(response.status_code == 200 for response in views)
    assert all('class="company-logo"' in response.text for response in views)
    assert all('src="/static/assert_logo.png"' in response.text for response in views)
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"


def test_owner_users_page_renders_role_aware_user_management_controls():
    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google-owner", "owner@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/users")

    assert response.status_code == 200
    assert 'data-dashboard-view="users"' in response.text
    assert 'href="/dashboard/users"' in response.text
    assert 'id="new-user"' in response.text
    assert 'id="users-table-body"' in response.text


def test_admin_users_page_can_only_offer_user_role_creation():
    from app.users.service import UserRole

    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google-admin", "admin@example.test", None, 3, UserRole.ADMIN)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/users")

    assert response.status_code == 200
    assert '<option value="USER">User</option>' in response.text
    assert '<option value="ADMIN">Admin</option>' not in response.text


def test_user_role_cannot_open_users_page_and_does_not_receive_management_controls():
    from app.users.service import UserRole

    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google-user", "user@example.test", None, 4, UserRole.USER)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        users = client.get("/dashboard/users")
        overview = client.get("/dashboard")
        devices = client.get("/dashboard/devices")

    assert users.status_code == 403
    assert users.headers["cache-control"] == "no-store"
    assert 'href="/dashboard/users"' not in overview.text
    assert 'id="new-project"' not in overview.text
    assert 'id="add-device"' not in devices.text


def test_development_dashboard_bypass_renders_a_fixed_local_identity_without_a_session():
    class StartupWarningCapture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    settings = Settings(
        env="development",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_development",
        dev_auth_bypass=True,
    )
    warning_capture = StartupWarningCapture()
    application_logger = logging.getLogger("app.main")
    application_logger.addHandler(warning_capture)
    try:
        with TestClient(create_app(settings), base_url="https://testserver") as client:
            response = client.get("/dashboard", follow_redirects=False)
    finally:
        application_logger.removeHandler(warning_capture)

    assert response.status_code == 200
    assert "local-development@skybeat.invalid" in response.text
    assert "DEVELOPMENT DASHBOARD AUTH BYPASS ENABLED" in warning_capture.messages
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_template_escapes_authenticated_identity_text():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "<script>alert(1)</script>", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/devices")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_page_contains_operational_sections_and_accessible_controls():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/devices")

    assert response.status_code == 200
    for identifier in (
        "project-filter",
        "state-filter",
        "gpu-state-filter",
        "dashboard-stale-warning",
        "last-refresh",
        "include-disabled",
        "reset-filters",
        "load-more",
    ):
        assert f'id="{identifier}"' in response.text
    assert 'for="search"' in response.text


def test_dashboard_script_renders_stage07_2_values_without_unsafe_html_or_client_state_rules():
    script = dashboard_script()

    assert '"Required Attention"' in script
    assert "function renderGpuSummary(payload)" in script
    assert 'value="AWAITING_FIRST_HEARTBEAT"' in dashboard_template()
    assert "item.state" in script
    assert "item.gpu_health?.effective" in script
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval("):
        assert unsafe_api not in script


def test_dashboard_filter_reload_clears_rows_before_requesting_a_fresh_first_page():
    script = dashboard_script()

    assert "const DEFAULT_PAGE_LIMIT = 50" in script
    assert 'query.set("cursor", cursor)' in script
    assert "resetDevicePagination();" in script


def test_dashboard_devices_uses_view_aware_opaque_cursor_history_and_sidebar_preference():
    script = dashboard_script()

    assert "const dashboardView = document.body.dataset.dashboardView" in script
    assert 'const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1"' in script
    assert "cursorHistory" in script
    assert "function currentCursor()" in script
    assert "requestDevices(currentCursor())" in script
    assert "cursorHistory = [null]" in script
    assert "pageIndex = 0" in script
    assert "window.location.reload" not in script
    assert "WebSocket" not in script
    assert "EventSource" not in script


def test_dashboard_devices_has_bounded_page_sizes_project_deep_links_and_keyboard_filters():
    script = dashboard_script()
    template = dashboard_template()

    assert 'id="page-size"' in template
    for page_size in ("25", "50", "100"):
        assert f'value="{page_size}"' in template
    assert "function applyDeviceFilter(name, value)" in script
    assert "function clearDeviceFilters()" in script
    assert "openFilterPopover" in script
    assert "closeFilterPopover" in script
    assert 'event.key === "Escape"' in script
    assert "filterOwner.focus()" in script
    assert 'new URL("/dashboard/devices", window.location.origin)' in script
    assert 'target.searchParams.set("project_id", project.project_id)' in script
    assert "CANONICAL_UUID" in script


def test_overview_leads_with_counts_and_required_attention_without_a_health_score():
    template = dashboard_template()
    script = dashboard_script()

    assert 'id="overview-health-meter"' not in template
    assert template.index('id="overview-cards"') < template.index('id="overview-attention"')
    assert template.index('id="overview-attention"') < template.index('id="overview-gpu-summary"')
    assert 'id="attention-heading">Required Attention' in template
    assert 'href="/dashboard/devices">View all devices' in template
    assert "counts.required_attention" in script


def test_ux6_fleet_strip_precedes_filters_and_incidents_use_existing_times():
    template = dashboard_template()
    script = dashboard_script()

    assert template.index('id="devices-workspace-summary"') < template.index('id="filters"')
    assert template.index('id="filters"') < template.index('class="device-table-region"')
    assert 'id="devices-summary-heading">Fleet state' in template
    assert 'className = "overview-incident-list"' in script
    assert "?incident=${encodeURIComponent(item.incident_id)}&point=${incidentPoint}" in script
    assert 'item.status === "CLOSED" ? item.closed_at : item.opened_at' in script
    assert "No recent incidents." in script


def test_required_attention_preview_renders_canonical_links_and_untrusted_text():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable")
    script = dashboard_script()
    controller = (
        "function renderAttention(items, total) {"
        + script.split("function renderAttention(items, total) {", 1)[1].split(
            "\nfunction renderRecentIncidents(items)", 1
        )[0]
    )
    harness = textwrap.dedent(
        """
        class Node {
          constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; }
          append(...items) { this.children.push(...items); }
          replaceChildren(...items) { this.children = items; }
          set innerHTML(_) { throw new Error("unsafe HTML rendering"); }
        }
        const document = { createElement: (tag) => new Node(tag) };
        const overviewAttention = new Node("div");
        const element = (tag, value) => {
          const node = new Node(tag);
          node.textContent = String(value);
          return node;
        };
        const displayValue = (value) => value ?? "—";
        const timestampNode = (value) => element("time", value ?? "Not seen yet");
        const statusPill = (value) => element("span", value);
        """
    )
    exercise = textwrap.dedent(
        """
        const item = {
          device_id: "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
          name: "<img src=x onerror=alert(1)>",
          project: { name: "<script>alert(2)</script>" },
          state: "OFFLINE", communication_attention: "OFFLINE",
          gpu_health: { effective: "DRIVER_ERROR" }, gpu_attention: true,
          last_seen_at: null,
        };
        renderAttention([item], 12);
        const row = overviewAttention.children[1].children[0];
        const identity = row.children[0].children[0];
        const primary = row.children[0].children[1];
        const supporting = row.children[1];
        if (identity.children[0].textContent !== item.name) throw new Error("device text changed");
        if (identity.children[0].href !== `/dashboard/devices/${item.device_id}`)
          throw new Error("wrong route");
        if (identity.children[1].textContent !== item.project.name)
          throw new Error("project text changed");
        if (primary.children[0].textContent !== "OFFLINE" ||
            primary.children[1].textContent !== "Communication offline" ||
            primary.children.length !== 2) throw new Error("primary reason is duplicated");
        if (supporting.children[0].children[0].textContent !== "GPU" ||
            supporting.children[0].children[1].textContent !== "DRIVER_ERROR")
          throw new Error("GPU state is missing or merged with communication");
        if (!overviewAttention.children[0].textContent.includes("1 of 12"))
          throw new Error("count missing");
        renderAttention([{ ...item, state: "ONLINE", communication_attention: null }], 1);
        const gpuPrimary = overviewAttention.children[1].children[0].children[0].children[1];
        if (gpuPrimary.children[0].textContent !== "ONLINE" ||
            gpuPrimary.children[1].textContent !== "GPU attention required")
          throw new Error("GPU-only reason is unclear");
        renderAttention([], 0);
        if (overviewAttention.children[0].textContent !== "No devices currently require attention.")
          throw new Error("empty state missing");
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "-e", harness + controller + exercise],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_required_attention_cards_are_width_capped_and_stack_on_narrow_screens():
    styles = dashboard_shell_styles()
    assert ".overview-required-attention .attention-list" in styles
    assert "max-width: 68rem" in styles
    assert ".attention-item__main" in styles
    assert ".attention-item__supporting" in styles
    assert ".overview-required-attention .attention-item { grid-template-columns: 1fr; }" in styles


def test_dashboard_active_view_refresh_preserves_current_page_and_reports_staleness():
    script = dashboard_script()

    assert "async function refreshActiveView()" in script
    assert "if (refreshing) return" in script
    assert "document.hidden ? 60000 : 15000" in script
    assert "requestDevices(currentCursor())" in script
    assert "Promise.allSettled" in script
    assert "Last successful refresh:" in script
    assert "Data stale - last updated" in script
    assert "WebSocket" not in script
    assert "EventSource" not in script


def test_dashboard_polling_waits_for_an_inflight_page_request_and_uses_visibility_cadence():
    script = dashboard_script()

    assert "async function refreshDashboard() {\n  if (refreshing || loadingDevices)" in script
    assert "document.hidden ? 60000 : 15000" in script
    assert 'document.addEventListener("visibilitychange"' in script
    assert "Promise.allSettled" in script
    assert "Data stale - last updated" in script
    assert "decode" not in script.lower()


def test_dashboard_page_contains_accessible_device_detail_drawer():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/devices")

    assert response.status_code == 200
    assert 'id="detail-panel"' in response.text
    assert 'aria-labelledby="detail-title"' in response.text
    assert 'id="detail-close"' in response.text
    assert 'id="detail-retry"' in response.text
    assert 'id="detail-incidents"' in response.text


def test_dashboard_detail_contains_bounded_history_controls_and_accessible_output():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/dashboard/devices")

    assert response.status_code == 200
    for identifier in (
        "history-range-controls",
        "history-status",
        "history-retry",
        "history-truncation",
        "history-content",
    ):
        assert f'id="{identifier}"' in response.text
    for range_name in ("1h", "6h", "24h", "7d"):
        assert f'data-history-range="{range_name}"' in response.text


def test_dashboard_history_uses_only_the_canonical_bounded_endpoint_and_native_svg():
    script = dashboard_script()

    assert 'const HISTORY_RANGES = ["1h", "6h", "24h", "7d"]' in script
    assert "fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/history?${query}`" in script
    assert 'query.set("range", rangeName)' in script
    assert "document.createElementNS" in script
    assert "historyGeneration" in script
    assert "heartbeat_samples" not in script
    assert "chart.js" not in script.lower()
    assert 'createElement("canvas")' not in script


def test_dashboard_history_source_guards_missing_zero_gpu_and_truncation_behavior():
    script = dashboard_script()

    assert "Number.isFinite(value)" in script
    assert "value === 0" in script
    assert "series.identity?.kind" in script
    assert "History was bounded by the server" in script
    assert "History could not be loaded." in script


def test_dashboard_history_marks_a_single_observation_without_inventing_a_segment():
    script = dashboard_script()

    assert "usable.length === 1" in script
    assert 'createSvgElement("circle")' in script


def test_dashboard_history_is_responsive_and_excludes_unbounded_or_external_renderers():
    styles = dashboard_styles()
    script = dashboard_script()

    assert ".history-chart" in styles
    assert re.search(r"max-width:\s*100%;", styles)
    assert "window.setInterval" not in script
    assert "void refreshOpenHistory();" in script
    assert "await refreshOpenHistory();" not in script
    assert "/heartbeats" not in script
    for unsafe_api in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
    ):
        assert unsafe_api not in script


def test_dashboard_detail_uses_canonical_bounded_endpoints_with_race_and_scope_guards():
    script = dashboard_script()

    assert "fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`" in script
    assert 'query.set("device_id", deviceId)' in script
    assert "detailButton.ariaLabel" in script
    assert "let detailGeneration" in script
    assert "AbortController" in script
    assert "refreshOpenDetail" in script
    assert "/alerts" not in script
    for unsafe_api in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
    ):
        assert unsafe_api not in script


def test_dashboard_detail_resets_its_title_before_a_new_canonical_request():
    script = dashboard_script()

    assert 'detailTitle.textContent = "Loading device detail…";' in script
    assert "detailTitle.focus();\n  resetDetailSections();" in script


def test_dashboard_detail_is_a_right_side_drawer_on_wide_screens():
    styles = dashboard_styles()

    assert re.search(r"@media\s*\(min-width:\s*1081px\)", styles)
    assert re.search(r"position:\s*fixed", styles)


def test_dashboard_history_excludes_raw_payloads_canvas_and_raw_json():
    script = dashboard_script()

    assert "/heartbeats" not in script
    assert 'createElement("canvas")' not in script
    assert "chart.js" not in script.lower()


def test_dashboard_page_has_one_semantic_sidebar_shell_and_operational_sections():
    template = dashboard_template()

    assert 'id="app-sidebar"' in template
    assert 'href="/dashboard"' in template
    assert 'href="/dashboard/devices"' in template
    assert 'href="/dashboard/projects"' in template
    assert 'id="dashboard-workspace"' in template
    assert 'id="add-device"' in template
    assert 'id="new-project"' in template


def test_dashboard_stage08b_shell_has_labelled_icon_navigation_and_page_context():
    template = dashboard_template()
    styles = dashboard_styles() + dashboard_shell_styles()

    for destination in ("overview", "devices", "projects"):
        assert f'data-nav-destination="{destination}"' in template
    assert 'class="nav-icon" aria-hidden="true"' in template
    assert 'class="nav-label"' in template
    assert 'aria-current="page"' in template
    assert 'id="page-title"' in template
    assert 'id="page-description"' in template
    assert "--sb-sidebar-width" in styles
    assert ".app-shell.sidebar-mobile-open" in styles
    assert '.sidebar-nav a[aria-current="page"]' in styles


def test_dashboard_stage08c_overview_contract_preserves_canonical_refresh_and_detail_flow():
    template = dashboard_template()
    script = dashboard_script()

    for identifier in (
        "overview-summary-status",
        "overview-gpu-summary",
        "overview-loading",
        "overview-error",
        "overview-attention",
    ):
        assert f'id="{identifier}"' in template
    assert "function renderGpuSummary(payload)" in script
    assert "deviceLink.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}`" in script
    assert "payload.required_attention" in script
    assert "requestOverview()" in script
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe_api not in script


def test_dashboard_stage08c_overview_keeps_each_canonical_device_state_and_refresh_truthful():
    script = dashboard_script()

    # Removing any canonical device state from the operational summary would
    # hide a condition that the server already owns and reports.
    for label in ("Online", "Suspect", "Offline", "Awaiting First Heartbeat"):
        assert f'["{label}", counts.' in script
    assert "Last successful refresh:" in script
    assert "attentionItems.sort" not in script


def test_dashboard_stage08c_uses_tokenized_state_hierarchy_without_reclassifying_gpu_data():
    script = dashboard_script()
    styles = dashboard_shell_styles()

    # Canonical labels drive presentation; the browser must not turn a numeric
    # GPU aggregate into a made-up health state or reorder server attention.
    assert 'overview-card--${label.toLowerCase().replaceAll(" ", "-")}' in script
    assert "statusPill(gpuProblems" not in script
    for selector in (
        ".overview-card--online",
        ".overview-card--suspect",
        ".overview-card--offline",
        ".overview-card--awaiting-first-heartbeat",
        ".attention-project",
    ):
        assert selector in styles


def test_dashboard_stage08c_summary_grid_accommodates_all_canonical_state_cards():
    styles = dashboard_styles() + dashboard_shell_styles()

    assert "grid-template-columns: repeat(auto-fit, minmax(8.2rem, 1fr))" in styles


def test_dashboard_stage08c_exposes_accessible_loading_empty_and_error_feedback():
    template = dashboard_template()
    script = dashboard_script()

    assert 'id="overview-loading" class="overview-feedback" aria-live="polite"' in template
    assert 'id="overview-error" class="overview-feedback" role="alert" hidden' in template
    for message in (
        "No devices are currently enrolled.",
        "No devices currently require attention.",
        "No recent incidents.",
        "Overview data could not be loaded. Existing data may be stale.",
        "Recent incident data could not be loaded. Overview data remains current.",
    ):
        assert message in script
    assert "deviceLink.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}`" in script
    assert "statusPill(item.gpu_health?.effective)" in script


def test_dashboard_stage08d_devices_workspace_reuses_canonical_inventory_contracts():
    template = dashboard_template()
    script = dashboard_script()
    styles = dashboard_shell_styles()

    for identifier in (
        "devices-workspace-summary",
        "devices-summary-cards",
        "devices-summary-status",
        "device-loading",
        "devices-result-context",
        "active-filters",
        "clear-device-filters",
        "reset-filters",
    ):
        assert f'id="{identifier}"' in template
    assert 'placeholder="Name, hostname, or UUID"' in template
    assert "function renderDeviceWorkspaceSummary(payload)" in script
    assert "requestOverview()" in script
    assert "function deviceFiltersAreActive()" in script
    assert "function clearDeviceFilter(name)" in script
    assert "No devices have been enrolled." in script
    assert "No devices match the current search or filters." in script
    assert "Unable to refresh the device list. Displayed device data was retained." in script
    assert (
        'const headers = ["Device", "Project", "Status", "OS", "GPU", "Last Seen", "Attention"]'
        in script
    )
    assert "device-identity__hostname" in script
    assert "function conciseOsLabel" in script
    assert "function deviceAttention" in script
    for selector in (
        ".devices-workspace-summary",
        ".devices-summary-cards",
        ".device-identity",
        ".device-row--attention",
        ".device-attention__item--communication",
        ".device-attention__item--gpu",
        ".device-loading",
    ):
        assert selector in styles
    assert "#device-status-table th:nth-child(2)" in styles
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe_api not in script


def test_dashboard_stage08d_preserves_one_polling_lifecycle_and_opaque_pagination():
    script = dashboard_script()

    assert script.count("function scheduleRefresh()") == 1
    assert script.count("window.setTimeout(refreshActiveView") == 1
    assert "const refreshCursor = currentCursor();" in script
    assert "const refreshPageIndex = pageIndex;" in script
    assert "currentCursor() === refreshCursor && pageIndex === refreshPageIndex" in script
    assert 'query.set("cursor", cursor)' in script
    assert "pageIndex += 1" in script
    assert "pageIndex -= 1" in script


def test_dashboard_visual_system_preserves_accessibility_and_responsive_behavior():
    styles = dashboard_styles()

    assert "prefers-reduced-motion" in styles
    assert "@media" in styles
    assert ":focus-visible" in styles
    assert re.search(r"position:\s*sticky", styles)


def test_dashboard_stage08a_defines_layered_design_tokens():
    styles = dashboard_styles()

    for token in (
        "--sb-color-slate-50",
        "--sb-space-1",
        "--sb-font-sans",
        "--sb-bg-app",
        "--sb-text-primary",
        "--sb-primary",
        "--sb-success",
        "--sb-warning",
        "--sb-danger",
        "--sb-info",
        "--sb-neutral",
        "--sb-control-bg",
        "--sb-button-primary-bg",
        "--sb-table-header-bg",
        "--sb-drawer-bg",
    ):
        assert token in styles

    assert styles.index("--sb-color-slate-50") < styles.index("--sb-bg-app")
    assert styles.index("--sb-bg-app") < styles.index("--sb-control-bg")


def test_dashboard_stage08a_foundations_keep_status_text_focus_and_density():
    styles = dashboard_styles()
    script = dashboard_script()

    assert ".status-pill::before" in styles
    assert re.search(r'content:\s*""', styles)
    assert ".status-online" in styles
    assert ".status-unknown" in styles
    assert "--sb-focus-ring" in styles
    assert ":focus-visible" in styles
    assert re.search(r"position:\s*sticky", styles)
    assert re.search(r"overflow-x:\s*auto", styles)
    assert 'status-${state.toLowerCase().replaceAll(/[ _]/g, "-")}' in script


def test_dashboard_stage08a_reuses_css_tokens_for_history_and_preserves_safe_dom():
    styles = dashboard_styles()
    script = dashboard_script()

    for token in (
        "--sb-history-series-1",
        "--sb-history-series-2",
        "--sb-history-series-3",
        "--sb-history-series-4",
    ):
        assert token in styles
    assert "const HISTORY_COLOR_TOKENS" in script
    assert "function historyColor(index)" in script
    assert "getComputedStyle(document.documentElement)" in script
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe_api not in script


def test_dashboard_stage08a_keeps_existing_template_contract_and_native_controls():
    template = dashboard_template()

    for identifier in (
        "app-sidebar",
        "dashboard-workspace",
        "project-filter",
        "state-filter",
        "gpu-state-filter",
        "detail-panel",
        "project-dialog",
        "device-enroll-dialog",
    ):
        assert f'id="{identifier}"' in template
    assert 'href="/dashboard"' in template
    assert 'href="/dashboard/devices"' in template
    assert 'href="/dashboard/projects"' in template


def test_dashboard_display_helpers_keep_canonical_states_and_exact_time_accessibility():
    script = dashboard_script()

    assert "formatRelativeTime" in script
    assert "setExactTimestamp" in script
    assert "AWAITING_FIRST_HEARTBEAT" in dashboard_template()
    assert "computeAvailability" not in script
    assert "deriveGpu" not in script


def test_dashboard_management_dialogs_expose_safe_canonical_controls():
    template = dashboard_template()

    for identifier in (
        "project-dialog",
        "project-form",
        "project-name",
        "project-status",
        "device-enroll-dialog",
        "device-enroll-form",
        "enroll-name",
        "enroll-project",
        "enroll-description",
        "enroll-submit",
        "detail-change-project",
        "detail-toggle-monitoring",
        "move-device-dialog",
        "monitoring-dialog",
    ):
        assert f'id="{identifier}"' in template
    assert "data-credential" not in template


def test_add_device_preparation_modal_has_only_operator_identity_fields():
    template = dashboard_template()
    modal = template.split('<dialog id="device-enroll-dialog"', 1)[1].split("</dialog>", 1)[0]
    assert 'id="enroll-name"' in modal
    assert 'id="enroll-project"' in modal
    assert 'id="enroll-description"' in modal
    assert 'id="enroll-description" name="description"' in modal
    assert "Prepare Device" in modal
    for removed in (
        "enroll-gpu-enabled",
        "enroll-gpu-count",
        "enrollment-credential",
        "save-enrollment-token",
        "copy-enrollment-credential",
        "download-agent-package",
        "refresh-enrollment-status",
        "revoke-enrollment",
        "reissue-enrollment",
    ):
        assert removed not in modal


def test_dashboard_management_uses_same_origin_mutations_without_browser_storage():
    script = dashboard_script()

    assert '"/api/v1/projects"' in script
    assert '"/api/v1/agent-enrollments"' in script
    assert 'method: "POST"' in script
    assert '"PATCH"' in script
    assert "sessionStorage" not in script
    assert "history.pushState" not in script


def test_alert_routing_page_uses_a_project_selector_and_a_polished_policy_editor():
    template = dashboard_template()
    script = dashboard_script()
    styles = dashboard_styles()

    assert '{% set page_title = "Alert Routing" %}' in template
    assert "Choose who receives operational alerts for each project." in template
    assert 'data-tooltip="Alert Routing"' in template
    assert '<span class="nav-label">Alert Routing</span>' in template
    assert 'id="notifications-list"' in template
    assert "alert-routing-page" in template
    assert "alert-routing-card" in script
    assert "notification-project-select" in script
    assert "Using fallback routing" in script
    assert "Custom routing" in script
    assert "Save routing policy" in script
    assert "Device stops reporting to SkyBeat." in script
    assert "Communication resumes after an offline incident." in script
    assert "SkyBeat detects confirmed GPU degradation." in script
    assert "GPU health returns to normal." in script
    assert "function renderLegacyNotificationProjects" not in script
    assert 'document.createElement("textarea")' not in script
    assert "notificationDraftPayload(draft)" in script
    assert "const reloaded = await requestNotifications()" in script
    assert "Discard changes" in script
    assert "Save failed. Your unsaved changes are still shown." in script
    assert ".alert-routing-page" in styles
    assert ".recipient-chip" in styles
    assert ".recipient-assignment-controls" in styles
    assert ".alert-routing-event" in styles


def test_alert_routing_assignment_controls_use_the_existing_active_user_directory():
    script = dashboard_script()

    assert "function renderRecipientChips" in script
    assert "notification-recipient-select" in script
    assert "requestUsers()" in script
    assert "user.active && !draft.recipients.has(user.email)" in script
    assert "No recipients assigned" in script
    assert "recipient-assignment" in script
    assert "recipient-chip__remove" in script
    assert "draft.recipients.delete(address)" in script
    assert 'element("span", address)' in script
    assert "recipientChip.innerHTML" not in script
    assert "Add email address" not in script
    assert 'credentials: "same-origin"' in script
    assert 'const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1"' in script
    assert "localStorage.setItem(SIDEBAR_PREFERENCE_KEY" in script


def test_alert_routing_assigns_active_users_and_keeps_project_drafts_isolated():
    node = shutil.which("node")
    assert node is not None
    harness = textwrap.dedent(
        """
        import fs from "node:fs";
        import vm from "node:vm";

        const source = fs.readFileSync(0, "utf8");
        const fallbackId = "11111111-1111-4111-8111-111111111111";
        const assignedId = "22222222-2222-4222-8222-222222222222";
        const zeroId = "33333333-3333-4333-8333-333333333333";
        const listeners = new WeakMap();
        const saved = [];
        let rejectNextSave = false;
        const projects = [
          {
            project_id: fallbackId,
            project_name: "Fallback project",
            configured: false,
            recipients: [],
            device_offline_enabled: true,
            device_recovered_enabled: true,
            gpu_degraded_enabled: true,
            gpu_recovered_enabled: true,
          },
          {
            project_id: assignedId,
            project_name: "Assigned project",
            configured: true,
            recipients: ["alice@example.test", "legacy@example.test"],
            device_offline_enabled: true,
            device_recovered_enabled: false,
            gpu_degraded_enabled: true,
            gpu_recovered_enabled: false,
          },
          {
            project_id: zeroId,
            project_name: "Zero-recipient project",
            configured: true,
            recipients: [],
            device_offline_enabled: true,
            device_recovered_enabled: true,
            gpu_degraded_enabled: true,
            gpu_recovered_enabled: true,
          },
        ];

        class Element {
          constructor(id = "") {
            this.id = id;
            this.attributes = new Map();
            this.children = [];
            this.classList = { add() {}, contains() { return false; }, remove() {}, toggle() {} };
            this.dataset = {};
            this.disabled = false;
            this.hidden = false;
            this.checked = false;
            this.open = false;
            this.selectedOptions = [];
            this.style = {};
            this.textContent = "";
            this.value = "";
          }
          addEventListener(type, listener) {
            const byType = listeners.get(this) ?? new Map();
            byType.set(type, listener);
            listeners.set(this, byType);
          }
          emit(type, event = {}) {
            const listener = listeners.get(this)?.get(type);
            return listener?.({ preventDefault() {}, target: this, ...event });
          }
          append(...children) {
            this.children.push(...children);
            this.firstChild = this.children[0] ?? null;
          }
          appendChild(child) { this.append(child); return child; }
          closest() { return null; }
          focus() {}
          getAttribute(name) { return this.attributes.get(name) ?? null; }
          querySelectorAll() { return []; }
          remove() {}
          removeAttribute(name) { this.attributes.delete(name); }
          replaceChildren(...children) {
            this.children = children;
            this.firstChild = children[0] ?? null;
          }
          reset() {}
          setAttribute(name, value) { this.attributes.set(name, String(value)); }
          showModal() { this.open = true; }
          close() { this.open = false; this.emit("close"); }
        }

        const elements = new Map();
        function elementFor(id) {
          if (!elements.has(id)) elements.set(id, new Element(id));
          return elements.get(id);
        }
        const document = {
          body: Object.assign(elementFor("body"), {
            dataset: {
              dashboardView: "notifications",
              dashboardRole: "ADMIN",
              canManage: "true",
            },
          }),
          addEventListener() {},
          createElement(tag) { return new Element(tag); },
          getElementById: elementFor,
          hidden: false,
          querySelector() { return elementFor("app-shell"); },
        };
        function response(payload) { return { ok: true, json: async () => payload }; }
        function failedResponse() { return { ok: false, json: async () => ({}) }; }
        async function fetch(path, options = {}) {
          if (path === "/api/v1/notifications") {
            return response({ items: projects.map((project) => ({
              ...project,
              recipients: [...project.recipients],
            })) });
          }
          if (path === "/api/v1/users") {
            return response({ items: [
              {
                user_id: 1,
                name: "Alice Example",
                email: "alice@example.test",
                role: "USER",
                active: true,
                created_at: "2026-09-30T00:00:00Z",
                updated_at: "2026-09-30T00:00:00Z",
              },
              {
                user_id: 2,
                name: "Bob Example",
                email: "bob@example.test",
                role: "ADMIN",
                active: true,
                created_at: "2026-09-30T00:00:00Z",
                updated_at: "2026-09-30T00:00:00Z",
              },
              {
                user_id: 3,
                name: "Inactive Example",
                email: "inactive@example.test",
                role: "USER",
                active: false,
                created_at: "2026-09-30T00:00:00Z",
                updated_at: "2026-09-30T00:00:00Z",
              },
            ] });
          }
          if (String(path) === `/api/v1/notifications/${zeroId}` && options.method === "PUT") {
            const payload = JSON.parse(options.body);
            saved.push(payload);
            if (rejectNextSave) return failedResponse();
            const project = projects.find((item) => item.project_id === zeroId);
            Object.assign(project, payload, { configured: true });
            return response({ notification: {
              project_id: zeroId,
              configured: true,
              recipients: payload.recipients,
            } });
          }
          throw new Error(`unexpected request ${path}`);
        }
        const window = {
          clearTimeout() {},
          location: { assign() {}, origin: "https://testserver", search: "" },
          matchMedia() { return { matches: false }; },
          setTimeout() { return 1; },
        };
        const context = {
          AbortController,
          Element,
          URL,
          URLSearchParams,
          console,
          document,
          fetch,
          localStorage: { getItem() { return null; }, setItem() {} },
          navigator: { clipboard: { writeText: async () => {} } },
          window,
        };
        vm.runInNewContext(source, context);
        for (let count = 0; count < 5; count += 1) await new Promise(setImmediate);

        function descendants(node) {
          return node.children.flatMap((child) => [child, ...descendants(child)]);
        }
        function currentNodes() { return descendants(elementFor("notifications-list")); }
        function withText(text) { return currentNodes().find((node) => node.textContent === text); }

        if (!withText("Using fallback routing")) throw new Error("fallback state was not rendered");
        let selector = currentNodes().find((node) => node.id === "notification-project-select");
        selector.value = assignedId;
        selector.emit("change");
        if (!withText("Alice Example")) throw new Error("assigned user name was not rendered");
        if (!withText("Email recipient") || !withText("legacy@example.test")) {
          throw new Error("existing email-only recipient was not preserved");
        }
        let recipientSelect = currentNodes().find(
          (node) => node.id === "notification-recipient-select",
        );
        if (currentNodes().some((node) => node.textContent.includes("Inactive Example"))) {
          throw new Error("inactive users must not be assignment choices");
        }
        recipientSelect.value = "bob@example.test";
        withText("Assign recipient").emit("click");
        if (!withText("Bob Example")) throw new Error("selected user was not assigned");

        selector = currentNodes().find((node) => node.id === "notification-project-select");
        selector.value = zeroId;
        selector.emit("change");
        if (!withText("Unsaved changes") || !withText("Alice Example")) {
          throw new Error("dirty project draft was not protected before switching");
        }
        withText("Discard changes").emit("click");
        selector = currentNodes().find((node) => node.id === "notification-project-select");
        selector.value = zeroId;
        selector.emit("change");
        if (!withText("No recipients assigned") || withText("Alice Example")) {
          throw new Error("zero-recipient project leaked the prior project draft");
        }

        recipientSelect = currentNodes().find(
          (node) => node.id === "notification-recipient-select",
        );
        recipientSelect.value = "bob@example.test";
        withText("Assign recipient").emit("click");
        const gpuDegraded = currentNodes().find(
          (node) => node.name === "gpu_degraded_enabled",
        );
        gpuDegraded.checked = false;
        gpuDegraded.emit("change");
        const save = currentNodes().find((node) => node.textContent === "Save routing policy");
        await save.emit("click");

        if (saved.length !== 1) throw new Error("routing policy was not saved once");
        const payload = saved[0];
        if (payload.recipients.join(",") !== "bob@example.test") {
          throw new Error(`unexpected recipients payload ${JSON.stringify(payload.recipients)}`);
        }
        if (payload.gpu_degraded_enabled !== false) {
          throw new Error("changed notification event policy was not persisted");
        }
        if (
          payload.device_offline_enabled !== true ||
          payload.device_recovered_enabled !== true ||
          payload.gpu_recovered_enabled !== true
        ) {
          throw new Error("unchanged notification event policy values were not preserved");
        }
        if (!withText("Saved") || !withText("Bob Example")) {
          throw new Error("saved server state was not rendered after reload");
        }
        const removeBob = currentNodes().find(
          (node) => node.getAttribute("aria-label") === "Remove Bob Example",
        );
        removeBob.emit("click");
        rejectNextSave = true;
        const retrySave = currentNodes().find(
          (node) => node.textContent === "Save routing policy",
        );
        await retrySave.emit("click");
        if (!withText("Save failed. Your unsaved changes are still shown.")) {
          throw new Error("failed save was presented as successful");
        }
        if (!withText("No recipients assigned") || saved.length !== 2) {
          throw new Error("failed save did not retain the visible recipient draft");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=dashboard_script(),
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr


def test_dashboard_enrollment_credential_is_transient_until_token_file_handoff():
    script = dashboard_script()

    assert "clearEnrollmentCredential" in script
    assert "enrollmentCredential = null" in script
    assert 'window.location.assign("/dashboard/deployments")' in script
    assert "deviceEnrollDialog.close" in script


def test_dashboard_deployment_flow_keeps_release_metadata_and_local_token_file_contract():
    template = dashboard_template()
    script = dashboard_script()

    assert 'id="deployments-list" class="deployment-grid"' in template
    assert 'fetch("/api/v1/agent-releases/current", { credentials: "same-origin" })' in script
    assert '"/api/v1/agent-releases/current/download"' in script
    assert "release.wheel_filename" in script
    assert "release.wheel_sha256" in script
    assert "cd ${release.archive_root}" in script
    assert "chmod +x ./install-agent.sh" in script
    assert "--token-file ./enrollment.token" in script
    assert "new Blob([enrollmentCredential]" in script
    assert "URL.createObjectURL" in script
    assert "URL.revokeObjectURL" in script
    assert 'window.location.assign("/dashboard/deployments")' in script
    enrollment_section = script[
        script.index("function submitEnrollment") : script.index("function openMoveDialog")
    ]
    assert "localStorage" not in enrollment_section
    assert "sessionStorage" not in enrollment_section


def test_dashboard_management_has_duplicate_submission_and_confirmation_guards():
    script = dashboard_script()

    for flag in (
        "projectSubmissionInFlight",
        "enrollmentSubmissionInFlight",
        "moveSubmissionInFlight",
        "monitoringSubmissionInFlight",
    ):
        assert flag in script
    assert 'id="detail-change-project"' in dashboard_template()
    assert 'id="detail-toggle-monitoring"' in dashboard_template()


def test_dashboard_new_project_preserves_the_add_device_draft_and_selects_the_new_project():
    script = dashboard_script()

    assert "pendingEnrollmentDraft" in script
    assert "draft.projectId = projectId" in script
    assert "openEnrollmentDialog(draft)" in script


def test_dashboard_project_refresh_populates_each_project_select_only_once():
    script = dashboard_script()

    assert "populateProjectSelect(projectFilter" in script
    assert "projectFilter.append(option)" not in script


def test_dashboard_never_uses_unsafe_html_and_only_stringifies_structured_mutation_bodies():
    script = dashboard_script()

    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe_api not in script
    assert "JSON.stringify(payload)" in script
    assert "renderRawJson" not in script


def test_dashboard_stage08e_reuses_one_diagnostic_drawer_for_overview_and_devices():
    template = dashboard_template()
    script = dashboard_script()
    styles = dashboard_shell_styles()

    assert '{% if active_view == "devices" or active_view == "overview" %}' in template
    for identifier in (
        "detail-identity-summary",
        "detail-state-summary",
        "detail-diagnostic-summary",
        "detail-resource-telemetry",
        "detail-panel",
    ):
        assert f'id="{identifier}"' in template
    for helper in (
        "function renderDetailIdentitySummary(device)",
        "function renderDetailStateSummary(device)",
        "function renderDiagnosticSummary(device)",
        "function renderResourceTelemetry(target, resources)",
        "function initializeSharedDetailDrawer()",
    ):
        assert helper in script
    assert 'detailManagementActions.hidden = dashboardView !== "devices"' in script
    assert "await refreshOpenDetail();" in script
    for selector in (
        ".detail-identity-summary",
        ".detail-state-summary",
        ".detail-resource-telemetry",
        ".detail-resource-meter",
    ):
        assert selector in styles


def test_dashboard_stage08e_keeps_canonical_evidence_history_and_safe_detail_race_handling():
    script = dashboard_script()

    assert "statusPill(device.state)" in script
    assert "statusPill(device.gpu_health?.effective)" in script
    assert '"Reported GPU state"' in script
    assert '"Telemetry sample collected"' in script
    assert '"Dashboard refresh"' in script
    assert "detailAbortController?.abort()" in script
    assert "detailLastSuccess = null;" in script
    assert "void refreshOpenHistory();" in script
    assert "function renderHistory(payload)" in script
    for unsafe_api in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe_api not in script


def test_dashboard_stage08f_sidebar_uses_icon_toggle_and_collapsed_navigation_tooltips():
    template = dashboard_template()
    script = dashboard_script()
    styles = dashboard_styles() + dashboard_shell_styles()

    assert 'id="sidebar-toggle-label"' in template
    assert "sidebar-toggle-icon--collapse" in template
    assert "sidebar-toggle-icon--expand" in template
    for label in ("Overview", "Devices", "Projects"):
        assert f'data-tooltip="{label}"' in template
    assert "function setSidebarTogglePresentation(collapsed)" in script
    assert 'sidebarToggle.classList.toggle("is-collapsed", collapsed)' in script
    assert (
        'setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);' in script
    )
    assert ".sidebar-collapsed .sidebar-nav a::after" in styles
    assert ".sidebar-toggle.is-collapsed .sidebar-toggle-icon--expand" in styles


def test_dashboard_stage08h_defines_an_intentional_icon_only_collapsed_brand_state():
    template = dashboard_template()
    styles = dashboard_styles() + dashboard_shell_styles()

    assert 'class="brand-mark"' in template
    assert 'class="brand-copy"' in template
    assert 'class="company-logo" src="/static/assert_logo.png"' in template
    assert ".app-shell.sidebar-collapsed .app-sidebar" in styles
    assert ".app-shell.sidebar-collapsed .app-sidebar { overflow: visible; }" in styles
    assert ".sidebar-collapsed .brand-lockup { align-items: center; display: grid;" in styles
    assert (
        ".sidebar-collapsed .brand-copy, .sidebar-collapsed .brand-subtitle { display: none; }"
        in styles
    )
    assert (
        ".sidebar-collapsed .sidebar-toggle { align-self: center; justify-self: center;" in styles
    )
    assert ".sidebar-collapsed .sidebar-nav a { justify-content: center;" in styles
    assert "transition: grid-template-columns .18s ease" in styles


def test_dashboard_stage08f_polishes_the_existing_add_device_enrollment_dialog():
    template = dashboard_template()
    script = dashboard_script()
    styles = dashboard_styles() + dashboard_shell_styles()

    assert 'class="dialog-close"' in template
    assert 'class="dialog-description"' in template
    assert 'class="sb-button--primary"' in template
    assert 'class="sb-button--secondary"' in template
    assert 'class="sb-button--ghost"' in template
    assert 'requestDashboardMutation("/api/v1/agent-enrollments", "POST"' in script
    assert "enrollmentSubmissionInFlight" in script
    assert ".dialog-close" in styles
    assert ".dialog-description" in styles
    assert ".dialog-actions" in styles
