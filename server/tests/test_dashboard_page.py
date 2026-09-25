import logging
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
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


def test_dashboard_page_redirects_unauthenticated_browser_to_google_login():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/google/login"
    assert "set-cookie" not in response.headers


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

    assert '"GPU Problems"' in script
    assert '"Active Incidents"' in script
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


def test_overview_health_meter_exposes_textual_canonical_online_counts():
    template = dashboard_template()
    script = dashboard_script()

    assert 'id="overview-health-meter"' in template
    assert 'id="overview-health-meter-label"' in template
    assert 'setAttribute("aria-label", healthText)' in script
    assert '"0 / 0 devices online"' in script


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
    assert "openDetail(item.device_id" in script
    assert "payload.attention" in script
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
    assert "inspect.ariaLabel = `Inspect ${displayValue(item.name)}`" in script
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
    assert 'const headers = ["Project", "Device / Host", "Availability", "GPU State"' in script
    assert "device-identity__uuid" in script
    assert "Inspect device" in script
    for selector in (
        ".devices-workspace-summary",
        ".devices-summary-cards",
        ".device-identity",
        ".device-row--attention",
        ".device-loading",
    ):
        assert selector in styles
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
    assert 'status-${displayValue(value).toLowerCase().replaceAll("_", "-")}' in script


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
        "enroll-gpu-enabled",
        "enroll-gpu-count",
        "enrollment-credential",
        "copy-enrollment-credential",
        "detail-change-project",
        "detail-toggle-monitoring",
        "move-device-dialog",
        "monitoring-dialog",
    ):
        assert f'id="{identifier}"' in template
    assert "data-credential" not in template


def test_dashboard_management_uses_same_origin_mutations_without_browser_storage():
    script = dashboard_script()

    assert '"/api/v1/projects"' in script
    assert '"/api/v1/devices"' in script
    assert 'method: "POST"' in script
    assert '"PATCH"' in script
    assert 'credentials: "same-origin"' in script
    assert 'const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1"' in script
    assert "localStorage.setItem(SIDEBAR_PREFERENCE_KEY" in script
    assert "sessionStorage" not in script
    assert "history.pushState" not in script


def test_dashboard_enrollment_credential_is_explicitly_transient_and_copy_only_on_action():
    script = dashboard_script()

    assert "clearEnrollmentCredential" in script
    assert "navigator.clipboard.writeText" in script
    assert "enrollmentCredential = null" in script
    assert "deviceEnrollDialog.close" in script


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
    assert 'requestDashboardMutation("/api/v1/devices", "POST"' in script
    assert "await refreshCanonicalDashboard();" in script
    assert "enrollmentSubmissionInFlight" in script
    assert ".dialog-close" in styles
    assert ".dialog-description" in styles
    assert ".dialog-actions" in styles


def test_dashboard_stage08g_keeps_successful_enrollment_truthful_when_inventory_refresh_fails():
    node = shutil.which("node")
    assert node is not None
    harness = textwrap.dedent(
        """
        import fs from "node:fs";
        import vm from "node:vm";

        const source = fs.readFileSync(0, "utf8");
        const projectId = "e3e70682-c209-4cac-a29f-6fbed82c07cd";
        const credential = "sb1.e3e70682-c209-4cac-a29f-6fbed82c07cd.test-secret";
        const listeners = new WeakMap();
        let failRendering = false;

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
          emit(type) {
            const listener = listeners.get(this)?.get(type);
            return listener?.({ key: "", preventDefault() {}, target: this });
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
        const intentionallyAbsent = new Set(["new-project"]);
        function elementFor(id) {
          if (!elements.has(id)) elements.set(id, new Element(id));
          return elements.get(id);
        }
        function pageElement(id) {
          return intentionallyAbsent.has(id) ? null : elementFor(id);
        }
        elementFor("enroll-gpu-enabled").checked = true;
        elementFor("enroll-gpu-count").value = "1";
        elementFor("page-size").value = "50";

        const document = {
          body: Object.assign(elementFor("body"), { dataset: { dashboardView: "devices" } }),
          addEventListener() {},
          createElement(tag) {
            if (failRendering) throw new Error("inventory render failed");
            return new Element(tag);
          },
          getElementById: pageElement,
          hidden: false,
          querySelector() { return elementFor("app-shell"); },
        };
        const response = (payload) => ({ ok: true, json: async () => payload });
        async function fetch(path, options = {}) {
          if (path === "/api/v1/devices" && options.method === "POST") {
            const payload = JSON.parse(options.body);
            if (
              payload.name !== "GPU node" ||
              payload.project_id !== projectId ||
              payload.gpu_monitoring_enabled !== true ||
              payload.expected_gpu_min_count !== 1
            ) throw new Error("unexpected enrollment payload");
            return response({ credential, device: { device_id: projectId, name: "GPU node" } });
          }
          if (String(path).startsWith("/api/v1/projects")) {
            return response({
              items: [{ project_id: projectId, name: "GPU Lab", device_counts: {} }],
              server_time: "2026-09-25T00:00:00Z",
            });
          }
          if (String(path).startsWith("/api/v1/dashboard/overview")) {
            return response({ counts: { total: 0 }, server_time: "2026-09-25T00:00:00Z" });
          }
          if (String(path).startsWith("/api/v1/devices?")) {
            return response({ items: [], next_cursor: null, server_time: "2026-09-25T00:00:00Z" });
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
        for (let count = 0; count < 10; count += 1) await new Promise(setImmediate);

        elementFor("add-device").emit("click");
        elementFor("enroll-name").value = "GPU node";
        elementFor("enroll-project").value = projectId;
        failRendering = true;
        elementFor("device-enroll-form").emit("submit");
        for (let count = 0; count < 10; count += 1) await new Promise(setImmediate);

        if (elementFor("enrollment-credential").textContent !== credential) {
          throw new Error("successful enrollment did not retain the credential");
        }
        if (elementFor("enrollment-credential-panel").hidden) {
          throw new Error("successful enrollment hid the one-time credential");
        }
        if (!elementFor("enrollment-status").textContent.startsWith("Device enrolled.")) {
          const message = elementFor("enrollment-status").textContent;
          throw new Error(`enrollment reported a false failure: ${message}`);
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - the test runs the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        check=False,
        input=dashboard_script(),
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
