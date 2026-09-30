import logging
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

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
        external = client.get("/login?next=https://attacker.example/")
        protected = client.get("/dashboard/devices", follow_redirects=False)

    assert login.status_code == 200
    assert 'href="/auth/google/login?next=/dashboard/devices"' in login.text
    assert "Continue with Google" in login.text
    assert 'src="/static/assert_logo.png"' in login.text
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


def test_dashboard_enrollment_credential_is_explicitly_transient_and_copy_only_on_action():
    script = dashboard_script()

    assert "clearEnrollmentCredential" in script
    assert "navigator.clipboard.writeText" in script
    assert "enrollmentCredential = null" in script
    assert "deviceEnrollDialog.close" in script


def test_dashboard_deployment_flow_uses_validated_release_metadata_and_a_local_token_file_only():
    template = dashboard_template()
    script = dashboard_script()

    for identifier in (
        "download-agent-package",
        "save-enrollment-token",
        "enrollment-install-instructions",
        "refresh-enrollment-status",
        "revoke-enrollment",
        "reissue-enrollment",
    ):
        assert f'id="{identifier}"' in template
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
    assert "`/api/v1/agent-enrollments/${encodeURIComponent(enrollmentId)}`" in script
    assert "if (!(await revokeEnrollment())) return;" in script
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
    assert "overflow-x: clip" in styles
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


def test_dashboard_stage08g_keeps_successful_enrollment_truthful_when_inventory_refresh_fails():
    node = shutil.which("node")
    assert node is not None
    harness = textwrap.dedent(
        """
        import fs from "node:fs";
        import vm from "node:vm";

        const source = fs.readFileSync(0, "utf8");
        const projectId = "e3e70682-c209-4cac-a29f-6fbed82c07cd";
        const enrollmentToken = "sbe1.e3e70682-c209-4cac-a29f-6fbed82c07cd.test-secret";
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
              if (path === "/api/v1/agent-releases/current") {
                return response({ release: {
                  wheel_filename: "skybeat_agent-1.0.0-cp312-none-any.whl",
                  wheel_sha256: "a".repeat(64),
                  archive_filename: "skybeat-agent-1.0.0-linux.zip",
                  archive_root: "skybeat-agent-1.0.0",
                  server_url: "https://testserver",
                  allow_insecure_local_server: false,
                }});
              }
              if (path === "/api/v1/agent-enrollments" && options.method === "POST") {
            const payload = JSON.parse(options.body);
            if (
              payload.mode !== "NEW" ||
              payload.name !== "GPU node" ||
              payload.project_id !== projectId ||
              payload.gpu_monitoring_enabled !== true ||
              payload.expected_gpu_min_count !== 1
            ) throw new Error("unexpected enrollment payload");
                return response({
                  token: enrollmentToken,
                  enrollment: { enrollment_id: projectId },
                });
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

        if (elementFor("enrollment-credential").textContent !== enrollmentToken) {
          throw new Error("successful enrollment did not retain the installer token");
        }
        if (elementFor("enrollment-credential-panel").hidden) {
          throw new Error("successful enrollment hid the one-time installer token");
        }
        if (!elementFor("enrollment-status").textContent.startsWith("Installer token created.")) {
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
