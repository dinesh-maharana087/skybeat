import logging
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


def test_dashboard_page_redirects_unauthenticated_browser_to_google_login():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/google/login"
    assert "set-cookie" not in response.headers


def test_authenticated_dashboard_routes_render_the_selected_view_only():
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
    assert "Live updates - updated" in script
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
    assert "max-width: 100%;" in styles
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

    assert "@media (min-width: 1081px)" in styles
    assert "position: fixed;" in styles


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


def test_dashboard_visual_system_preserves_accessibility_and_responsive_behavior():
    styles = dashboard_styles()

    assert "prefers-reduced-motion" in styles
    assert "@media" in styles
    assert ":focus-visible" in styles
    assert "position: sticky" in styles


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
