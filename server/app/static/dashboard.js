"use strict";

const DEFAULT_PAGE_LIMIT = 50;
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const VISIBLE_REFRESH_MS = 15000;
const HIDDEN_REFRESH_MS = 60000;
const SEARCH_DEBOUNCE_MS = 250;
const LOG_PAGE_LIMIT = 60;
const LOG_SOURCE_LABELS = { skybeat_agent: "SkyBeat Agent", system_journal: "System", kernel: "Kernel" };
const LOG_RANGE_MS = { "15m": 900000, "1h": 3600000, "6h": 21600000, "24h": 86400000, "7d": 604800000 };
const HISTORY_RANGES = ["1h", "6h", "24h", "7d"];
const HISTORY_COLOR_TOKENS = [
  "--sb-history-series-1",
  "--sb-history-series-2",
  "--sb-history-series-3",
  "--sb-history-series-4",
];
const dashboardView = document.body.dataset.dashboardView;
const dashboardRole = document.body.dataset.dashboardRole;
const canManage = document.body.dataset.canManage === "true";
const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1";
const appShell = document.querySelector(".app-shell");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarToggleLabel = document.getElementById("sidebar-toggle-label");
const logout = document.getElementById("logout");

const devices = document.getElementById("devices");
const deviceEmpty = document.getElementById("device-empty");
const deviceError = document.getElementById("device-error");
const deviceLoading = document.getElementById("device-loading");
const devicesResultContext = document.getElementById("devices-result-context");
const devicesSummaryCards = document.getElementById("devices-summary-cards");
const devicesSummaryStatus = document.getElementById("devices-summary-status");
const refreshStatus = document.getElementById("refresh-status");
const lastRefresh = document.getElementById("last-refresh");
const staleWarning = document.getElementById("dashboard-stale-warning");
const overviewCards = document.getElementById("overview-cards");
const overviewStatus = document.getElementById("overview-status");
const overviewLoading = document.getElementById("overview-loading");
const overviewError = document.getElementById("overview-error");
const overviewSummaryStatus = document.getElementById("overview-summary-status");
const overviewGpuSummary = document.getElementById("overview-gpu-summary");
const awaitingFirstHeartbeat = document.getElementById("awaiting-first-heartbeat");
const projectSummary = document.getElementById("project-summary-content");
const overviewAttention = document.getElementById("overview-attention");
const overviewIncidents = document.getElementById("overview-incidents");
const projectFilter = document.getElementById("project-filter");
const stateFilter = document.getElementById("state-filter");
const gpuStateFilter = document.getElementById("gpu-state-filter");
const search = document.getElementById("search");
const includeDisabled = document.getElementById("include-disabled");
const filters = document.getElementById("filters");
const resetFilters = document.getElementById("reset-filters");
const loadMore = document.getElementById("load-more");
const previousPage = document.getElementById("previous-page");
const pageContext = document.getElementById("page-context");
const activeFilters = document.getElementById("active-filters");
const pageSize = document.getElementById("page-size");
const clearDeviceFiltersButton = document.getElementById("clear-device-filters");
const detailPanel = document.getElementById("detail-panel");
const detailOpenPage = document.getElementById("detail-open-page");
const deviceDetailPage = document.getElementById("device-detail-page");
const lifecycleStatus = document.getElementById("agent-lifecycle-status");
const lifecycleFacts = document.getElementById("agent-lifecycle-facts");
const lifecycleUpgrade = document.getElementById("agent-lifecycle-upgrade");
const lifecycleRollback = document.getElementById("agent-lifecycle-rollback");
let lifecycleGeneration = 0;
let lifecycleState = null;
let lifecycleAvailable = false;
let lifecycleSubmitting = false;
let lastLogAttemptAt = 0;
const logWatchState = {
  source: "", range: "24h", q: "", window: null, items: [], sources: [], nextCursor: null,
  hasSuccess: false, olderLoaded: false, generation: 0, controller: null,
  loading: false, offline: false, latestSuccessfulAt: null, contextWindow: null,
};
const incidentDiagnosticsState = { generation: 0, listGeneration: 0, controller: null, payload: null };
const detailTitle = document.getElementById("detail-title");
const detailStatus = document.getElementById("detail-status");
const detailRetry = document.getElementById("detail-retry");
const detailClose = document.getElementById("detail-close");
const detailIdentitySummary = document.getElementById("detail-identity-summary");
const detailStateSummary = document.getElementById("detail-state-summary");
const detailDiagnosticSummary = document.getElementById("detail-diagnostic-summary");
const detailIdentity = document.getElementById("detail-identity");
const detailFreshness = document.getElementById("detail-freshness");
const detailSystem = document.getElementById("detail-system");
const detailResourceTelemetry = document.getElementById("detail-resource-telemetry");
const detailStorage = document.getElementById("detail-storage");
const detailGpus = document.getElementById("detail-gpus");
const detailPolicy = document.getElementById("detail-policy");
const detailIncidents = document.getElementById("detail-incidents");
const historyRangeControls = document.getElementById("history-range-controls");
const historyStatus = document.getElementById("history-status");
const historyRetry = document.getElementById("history-retry");
const historyTruncation = document.getElementById("history-truncation");
const historyContent = document.getElementById("history-content");
const newProject = document.getElementById("new-project");
const addDevice = document.getElementById("add-device");
const projectDialog = document.getElementById("project-dialog");
const projectForm = document.getElementById("project-form");
const projectName = document.getElementById("project-name");
const projectStatus = document.getElementById("project-status");
const projectSubmit = document.getElementById("project-submit");
const projectClose = document.getElementById("project-close");
const projectCancel = document.getElementById("project-cancel");
const deviceEnrollDialog = document.getElementById("device-enroll-dialog");
const deviceEnrollForm = document.getElementById("device-enroll-form");
const enrollName = document.getElementById("enroll-name");
const enrollProject = document.getElementById("enroll-project");
const enrollDescription = document.getElementById("enroll-description");
const enrollmentStatus = document.getElementById("enrollment-status");
const enrollSubmit = document.getElementById("enroll-submit");
const deviceEnrollClose = document.getElementById("device-enroll-close");
const enrollCancel = document.getElementById("enroll-cancel");
const newProjectFromEnroll = document.getElementById("new-project-from-enroll");
const detailManagementActions = document.getElementById("detail-management-actions");
const detailChangeProject = document.getElementById("detail-change-project");
const detailToggleMonitoring = document.getElementById("detail-toggle-monitoring");
const moveDeviceDialog = document.getElementById("move-device-dialog");
const moveDeviceForm = document.getElementById("move-device-form");
const moveDeviceProject = document.getElementById("move-device-project");
const moveDeviceDescription = document.getElementById("move-device-description");
const moveDeviceStatus = document.getElementById("move-device-status");
const moveDeviceSubmit = document.getElementById("move-device-submit");
const monitoringDialog = document.getElementById("monitoring-dialog");
const monitoringForm = document.getElementById("monitoring-form");
const monitoringDescription = document.getElementById("monitoring-description");
const monitoringStatus = document.getElementById("monitoring-status");
const monitoringSubmit = document.getElementById("monitoring-submit");
const usersTableBody = document.getElementById("users-table-body");
const usersStatus = document.getElementById("users-status");
const usersEmpty = document.getElementById("users-empty");
const newUser = document.getElementById("new-user");
const userDialog = document.getElementById("user-dialog");
const userForm = document.getElementById("user-form");
const userName = document.getElementById("user-name");
const userEmail = document.getElementById("user-email");
const userRole = document.getElementById("user-role");
const userActive = document.getElementById("user-active");
const userFormStatus = document.getElementById("user-form-status");
const userSubmit = document.getElementById("user-submit");
const userClose = document.getElementById("user-close");
const userCancel = document.getElementById("user-cancel");
const notificationsList = document.getElementById("notifications-list");
const notificationsStatus = document.getElementById("notifications-status");
const deploymentsList = document.getElementById("deployments-list");
const deploymentsStatus = document.getElementById("deployments-status");
const deploymentsEmpty = document.getElementById("deployments-empty");
const releaseRegisterForm = document.getElementById("release-register-form");
const releaseRegisterName = document.getElementById("release-register-name");
const releaseRegisterSubmit = document.getElementById("release-register-submit");
const releaseManagementStatus = document.getElementById("release-management-status");
const releaseActiveStatus = document.getElementById("release-active-status");
const releaseList = document.getElementById("release-list");
const deploymentDeleteDialog = document.getElementById("deployment-delete-dialog");
const deploymentDeleteStatus = document.getElementById("deployment-delete-status");
const deploymentDeleteConfirm = document.getElementById("deployment-delete-confirm");
const deploymentDeleteCancel = document.getElementById("deployment-delete-cancel");

let refreshTimer = null;
let searchTimer = null;
let refreshing = false;
let loadingDevices = false;
let nextCursor = null;
let cursorHistory = [null];
let pageIndex = 0;
let lastSuccessfulRefresh = null;
let overviewTotal = null;
let editingUserId = null;
let selectedDeviceId = null;
let detailGeneration = 0;
let detailAbortController = null;
let detailLastSuccess = null;
let detailOrigin = null;
let selectedHistoryRange = "1h";
let historyGeneration = 0;
let historyAbortController = null;
let historyLastSuccess = null;
let latestProjects = [];
let currentDetail = null;
let enrollmentCredential = null;
let enrollmentId = null;
let enrollmentPreparedWithoutToken = false;
let projectSubmissionInFlight = false;
let enrollmentSubmissionInFlight = false;
let moveSubmissionInFlight = false;
let monitoringSubmissionInFlight = false;
let projectOpenedFromEnrollment = false;
let pendingEnrollmentDraft = null;
let pendingMonitoringEnabled = null;
let pageLimit = DEFAULT_PAGE_LIMIT;
let requestedProjectId = null;
let activeFilterPopover = null;
let filterOwner = null;
let notificationProjects = [];
let selectedNotificationProjectId = null;
let notificationUsers = [];
let notificationDraft = null;
let notificationSaveState = "unchanged";
let notificationSaveMessage = "No changes.";
let notificationSaveInFlight = false;
let notificationDirectoryAvailable = true;
let notificationDevices = [];
let selectedNotificationDeviceId = null;
let notificationDeviceDraft = null;
let notificationDeviceSaveState = "unchanged";
let notificationDeviceSaveMessage = "No changes.";
let notificationDeviceSaveInFlight = false;
let notificationDeviceLoadState = "loading";
let notificationDeviceRequestId = 0;
let toInstallDeployments = [];
let deploymentRelease = null;
let pendingDeploymentDeletion = null;

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  return node;
}

function displayValue(value) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatPercent(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value}%` : "—";
}

function formatRelativeTime(value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "—";
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (Math.abs(seconds) < 60) return "just now";
  const units = [
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ];
  for (const [unitSeconds, label] of units) {
    const amount = Math.round(Math.abs(seconds) / unitSeconds);
    if (amount >= 1) {
      const suffix = amount === 1 ? "" : "s";
      return seconds >= 0 ? `${amount} ${label}${suffix} ago` : `in ${amount} ${label}${suffix}`;
    }
  }
  return "just now";
}

function setExactTimestamp(node, value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    node.removeAttribute("title");
    return;
  }
  node.title = new Date(timestamp).toISOString();
}

function timestampNode(value) {
  const node = element("span", formatRelativeTime(value));
  setExactTimestamp(node, value);
  return node;
}

function statusPill(value) {
  const state = displayValue(value);
  const labels = {
    AWAITING_FIRST_HEARTBEAT: "Awaiting first heartbeat",
    NVIDIA_SMI_FAILED: "NVIDIA SMI failed",
    GPU_MISSING: "GPU missing",
    DRIVER_ERROR: "Driver error",
    NOT_MONITORED: "Not monitored",
    NOT_REPORTED: "Not reported",
    TOKEN_EXPIRED: "Token expired",
  };
  const node = element("span", labels[state] ?? state.replaceAll("_", " "));
  node.className = `status-pill status-${state.toLowerCase().replaceAll(/[ _]/g, "-")}`;
  return node;
}

function setVisible(node, visible) {
  if (node === null) return;
  node.hidden = !visible;
}

function currentCursor() {
  return cursorHistory[pageIndex] ?? null;
}

function resetDevicePagination() {
  cursorHistory = [null];
  pageIndex = 0;
  nextCursor = null;
}

function setSidebarTogglePresentation(collapsed) {
  if (sidebarToggle === null) return;
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  sidebarToggle.classList.toggle("is-collapsed", collapsed);
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggle.setAttribute("aria-label", label);
  sidebarToggle.title = label;
  if (sidebarToggleLabel !== null) sidebarToggleLabel.textContent = label;
}

function setSidebarCollapsed(collapsed) {
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  setSidebarTogglePresentation(collapsed);
  if (isMobile) {
    appShell?.classList.toggle("sidebar-mobile-open", !collapsed);
    return;
  }
  appShell?.classList.remove("sidebar-mobile-open");
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem(SIDEBAR_PREFERENCE_KEY, collapsed ? "collapsed" : "expanded");
}

function toggleSidebar() {
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  const collapsed = isMobile
    ? !appShell?.classList.contains("sidebar-mobile-open")
    : !appShell?.classList.contains("sidebar-collapsed");
  setSidebarCollapsed(collapsed);
}

document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    window.matchMedia("(max-width: 900px)").matches &&
    appShell?.classList.contains("sidebar-mobile-open")
  ) {
    setSidebarCollapsed(true);
    sidebarToggle?.focus();
  }
});

function clearDeviceMessages() {
  setVisible(deviceEmpty, false);
  setVisible(deviceError, false);
}

function deviceQuery(cursor = null) {
  const query = new URLSearchParams({ limit: String(pageLimit) });
  const selectedProject = projectFilter?.value || requestedProjectId;
  if (selectedProject) query.set("project_id", selectedProject);
  if (stateFilter.value) query.set("state", stateFilter.value);
  if (gpuStateFilter.value) query.set("gpu_state", gpuStateFilter.value);
  if (search.value.trim()) query.set("search", search.value.trim());
  if (includeDisabled.checked) query.set("include_disabled", "true");
  if (cursor) query.set("cursor", cursor);
  return query;
}

async function requestOverview() {
  const response = await fetch("/api/v1/dashboard/overview", { credentials: "same-origin" });
  if (!response.ok) throw new Error("overview request failed");
  return response.json();
}

async function requestDevices(cursor = null) {
  const response = await fetch(`/api/v1/devices?${deviceQuery(cursor)}`, {
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("device request failed");
  return response.json();
}

async function requestProjects() {
  const response = await fetch("/api/v1/projects", { credentials: "same-origin" });
  if (!response.ok) throw new Error("project request failed");
  return response.json();
}

async function requestUsers() {
  const response = await fetch("/api/v1/users", { credentials: "same-origin" });
  if (!response.ok) throw new Error("users request failed");
  return response.json();
}

async function requestNotifications() {
  const response = await fetch("/api/v1/notifications", { credentials: "same-origin" });
  if (!response.ok) throw new Error("notifications request failed");
  return response.json();
}

async function requestNotificationDevices(projectId) {
  const response = await fetch(
    `/api/v1/notifications/${encodeURIComponent(projectId)}/devices`,
    { credentials: "same-origin" },
  );
  if (!response.ok) throw new Error("notification devices request failed");
  return response.json();
}

async function requestToInstallDeployments() {
  const response = await fetch("/api/v1/agent-enrollments", { credentials: "same-origin" });
  if (!response.ok) throw new Error("deployment request failed");
  const payload = await response.json();
  if (!Array.isArray(payload?.items)) throw new Error("deployment response was invalid");
  return payload.items;
}

async function requestRecentIncidents() {
  const response = await fetch("/api/v1/incidents?limit=10", { credentials: "same-origin" });
  if (!response.ok) throw new Error("incident request failed");
  return response.json();
}

async function requestDashboardMutation(path, method, payload) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let responsePayload = null;
  try {
    responsePayload = await response.json();
  } catch (_) {
    responsePayload = null;
  }
  if (!response.ok) {
    const error = new Error("dashboard management request failed");
    error.status = response.status;
    throw error;
  }
  return responsePayload;
}

function projectCreationErrorMessage(error) {
  const status = error instanceof Error ? error.status : null;
  if (status === 401) return "Your session has expired. Sign in again.";
  if (status === 403) return "You no longer have permission to create projects.";
  if (status === 409) return "A project change conflicts with the current state. Refresh and try again.";
  if (status === 422) return "Enter a valid project name and try again.";
  return "Project could not be created. Check the name and try again.";
}

function renderOverview(payload) {
  const counts = payload.counts ?? {};
  overviewTotal = typeof counts.total === "number" ? counts.total : null;
  const cards = [
    ["Total Devices", counts.total],
    ["Online", counts.online],
    ["Suspect", counts.suspect],
    ["Offline", counts.offline],
    ["Required Attention", counts.required_attention],
  ];
  const nodes = cards.map(([label, value]) => {
    const card = document.createElement("article");
    card.className = `overview-card overview-card--${label.toLowerCase().replaceAll(" ", "-")}`;
    card.append(element("h3", label), element("p", displayValue(value)));
    return card;
  });
  overviewCards?.replaceChildren(...nodes);
  if (overviewLoading !== null) overviewLoading.hidden = true;
  if (overviewError !== null) overviewError.hidden = true;
  if (overviewSummaryStatus !== null) {
    overviewSummaryStatus.textContent = counts.total === 0 ? "No devices are currently enrolled." : "Current canonical fleet state.";
  }
  if (awaitingFirstHeartbeat !== null) {
    awaitingFirstHeartbeat.textContent = `Awaiting first heartbeat: ${displayValue(
      counts.awaiting_first_heartbeat
    )}`;
  }
  renderGpuSummary(payload);
  if (overviewStatus !== null) {
    overviewStatus.textContent = `Overview updated ${formatRelativeTime(payload.server_time)}`;
    setExactTimestamp(overviewStatus, payload.server_time);
  }
  renderAttention(payload.required_attention, counts.required_attention);
  renderProjects(payload.projects, payload.projects_truncated === true);
}

function renderGpuSummary(payload) {
  if (overviewGpuSummary === null) return;
  const gpuProblems = payload.counts?.gpu_problem;
  const summary = document.createElement("p");
  if (typeof gpuProblems !== "number") {
    summary.append("GPU aggregate is unavailable.");
  } else if (gpuProblems === 0) {
    summary.append("No GPU problems are currently reported.");
  } else {
    summary.append(
      element("strong", `${gpuProblems} device${gpuProblems === 1 ? "" : "s"}`),
      " require GPU attention."
    );
  }
  overviewGpuSummary.replaceChildren(summary);
}

function renderDeviceWorkspaceSummary(payload) {
  const counts = payload.counts ?? {};
  overviewTotal = typeof counts.total === "number" ? counts.total : null;
  const cards = [
    ["Total", counts.total],
    ["Online", counts.online],
    ["Suspect", counts.suspect],
    ["Offline", counts.offline],
    ["Awaiting First Heartbeat", counts.awaiting_first_heartbeat],
  ];
  if (devicesSummaryCards !== null) {
    const nodes = cards.map(([label, value]) => {
      const card = document.createElement("span");
      card.className = `devices-summary-card devices-summary-card--${label.toLowerCase().replaceAll(" ", "-")}`;
      card.append(element("strong", displayValue(value)), element("span", label));
      return card;
    });
    devicesSummaryCards.replaceChildren(...nodes);
  }
  if (devicesSummaryStatus !== null) {
    devicesSummaryStatus.textContent = "Canonical fleet availability from the server.";
  }
}

function showDeviceWorkspaceSummaryError() {
  if (devicesSummaryStatus !== null) {
    devicesSummaryStatus.textContent = "Fleet summary could not be refreshed. Existing summary may be stale.";
  }
}

function renderAttention(items, total) {
  if (overviewAttention === null) return;
  const attentionItems = Array.isArray(items) ? items : [];
  if (!attentionItems.length) {
    overviewAttention.replaceChildren(element("p", total === 0 ? "No devices currently require attention." : "Required attention is temporarily unavailable."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "attention-list";
  for (const item of attentionItems) {
    const row = document.createElement("li");
    row.className = "attention-item";
    const main = document.createElement("div");
    main.className = "attention-item__main";
    const identity = document.createElement("div");
    identity.className = "attention-item__identity";
    const deviceLink = element("a", displayValue(item.name));
    deviceLink.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}`;
    deviceLink.className = "attention-device-link";
    const projectContext = element("span", displayValue(item.project?.name));
    projectContext.className = "attention-project";
    identity.append(deviceLink, projectContext);
    const primary = document.createElement("div");
    primary.className = "attention-item__primary";
    const communicationAttention = item.communication_attention;
    const reason = element("strong", communicationAttention ? `Communication ${String(communicationAttention).toLowerCase()}` : "GPU attention required");
    reason.className = "attention-reason";
    primary.append(statusPill(item.state), reason);
    main.append(identity, primary);

    const supporting = document.createElement("div");
    supporting.className = "attention-item__supporting";
    const gpu = document.createElement("div");
    gpu.className = item.gpu_attention === true ? "attention-item__gpu attention-item__gpu--attention" : "attention-item__gpu";
    gpu.append(element("span", "GPU"), statusPill(item.gpu_health?.effective));
    const lastSeen = element("span", "Last seen: ");
    lastSeen.append(item.last_seen_at ? timestampNode(item.last_seen_at) : element("span", "Not seen yet"));
    lastSeen.className = "attention-last-seen";
    supporting.append(gpu, lastSeen);
    row.append(main, supporting);
    list.append(row);
  }
  const shown = element("p", `Showing ${attentionItems.length} of ${displayValue(total)} devices requiring attention.`);
  shown.className = "attention-preview-count";
  overviewAttention.replaceChildren(shown, list);
}

function renderRecentIncidents(items) {
  if (overviewIncidents === null) return;
  const incidentItems = Array.isArray(items) ? items : [];
  if (!incidentItems.length) {
    overviewIncidents.replaceChildren(element("p", "No recent incidents."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "overview-incident-list";
  for (const item of incidentItems) {
    const row = document.createElement("li");
    row.className = "overview-incident";
    const identity = document.createElement("div");
    identity.className = "overview-incident__identity";
    const device = element("a", displayValue(item.device_name));
    const incidentPoint = item.status === "CLOSED" ? "recovered" : "opened";
    device.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}?incident=${encodeURIComponent(item.incident_id)}&point=${incidentPoint}`;
    const type = element("span", displayValue(item.type).replaceAll("_", " ").toLowerCase());
    type.className = "overview-incident__type";
    identity.append(device, type);
    const state = statusPill(item.status);
    const time = element("span", item.status === "CLOSED" ? "Closed " : "Opened ");
    time.className = "overview-incident__time";
    time.append(timestampNode(item.status === "CLOSED" ? item.closed_at : item.opened_at));
    row.append(identity, state, time);
    list.append(row);
  }
  overviewIncidents.replaceChildren(list);
}

function renderProjects(projects, truncated) {
  const selectedProject = projectFilter?.value || requestedProjectId || "";
  const projectItems = Array.isArray(projects) ? projects : [];
  latestProjects = projectItems;
  if (projectFilter !== null) populateProjectSelect(projectFilter, "All projects", selectedProject);
  if (enrollProject !== null) {
    populateProjectSelect(enrollProject, "Select a project", enrollProject.value);
  }
  if (moveDeviceProject !== null) {
    populateProjectSelect(moveDeviceProject, "Select a project", moveDeviceProject.value);
  }
  const summary = document.createElement("ul");
  summary.className = "project-list";
  for (const project of projectItems) {
    const counts = project.device_counts ?? {};
    const item = document.createElement("li");
    item.className = "project-card";
    const link = element("a", displayValue(project.name));
    const target = new URL("/dashboard/devices", window.location.origin);
    target.searchParams.set("project_id", project.project_id);
    link.href = `${target.pathname}?${target.searchParams}`;
    item.append(
      link,
      element(
        "span",
        `Total ${displayValue(counts.total)} · Online ${displayValue(counts.online)} · ` +
          `Suspect ${displayValue(counts.suspect)} · Offline ${displayValue(counts.offline)} · ` +
          `Awaiting ${displayValue(counts.awaiting_first_heartbeat)}`
      )
    );
    summary.append(item);
  }
  if (projectSummary === null) return;
  if (!projectItems.length) {
    projectSummary.replaceChildren(element("p", "No projects are available."));
    return;
  }
  if (truncated) summary.append(element("li", "Additional projects are not shown."));
  projectSummary.replaceChildren(summary);
}

function populateProjectSelect(select, placeholder, selectedProject) {
  select.replaceChildren(element("option", placeholder));
  select.firstChild.value = "";
  for (const project of latestProjects) {
    const option = element("option", displayValue(project.name));
    option.value = displayValue(project.project_id);
    if (option.value === selectedProject) option.selected = true;
    select.append(option);
  }
}

async function refreshProjectList() {
  const payload = await requestProjects();
  renderProjects(payload.items, false);
}

async function refreshCanonicalDashboard() {
  await refreshActiveView();
  if (dashboardView === "devices") {
    try {
      await refreshProjectList();
    } catch (_) {
      refreshStatus.textContent = "Project list refresh failed. Existing project data was retained.";
    }
  }
}

function tableHeader() {
  const table = document.createElement("table");
  table.id = "device-status-table";
  const headers = ["Device", "Project", "Status", "OS", "GPU", "Last Seen", "Attention"];
  const row = document.createElement("tr");
  for (const name of headers) {
    const cell = document.createElement("th");
    const filterName = {
      Project: "project_id",
      Status: "state",
      GPU: "gpu_state",
    }[name];
    if (filterName) {
      const button = element("button", `${name} ▾`);
      button.type = "button";
      button.ariaLabel = `Filter ${name}`;
      button.className = "filter-toggle";
      button.dataset.filterName = filterName;
      button.setAttribute("aria-expanded", "false");
      cell.append(button);
    } else cell.textContent = name;
    row.append(cell);
  }
  const head = document.createElement("thead");
  head.append(row);
  table.append(head, document.createElement("tbody"));
  return table;
}

function filterOptions(name) {
  if (name === "project_id") {
    return [["", "All projects"], ...latestProjects.map((project) => [project.project_id, project.name])];
  }
  if (name === "state") {
    return [["", "All availability states"], ["ONLINE", "ONLINE"], ["SUSPECT", "SUSPECT"], ["OFFLINE", "OFFLINE"], ["AWAITING_FIRST_HEARTBEAT", "AWAITING_FIRST_HEARTBEAT"]];
  }
  return [["", "All GPU states"], ["OK", "OK"], ["GPU_MISSING", "GPU_MISSING"], ["NVIDIA_SMI_FAILED", "NVIDIA_SMI_FAILED"], ["DRIVER_ERROR", "DRIVER_ERROR"], ["UNKNOWN", "UNKNOWN"], ["NOT_MONITORED", "NOT_MONITORED"]];
}

function closeFilterPopover({ restoreFocus = true } = {}) {
  if (activeFilterPopover === null) return;
  activeFilterPopover.remove();
  activeFilterPopover = null;
  filterOwner?.setAttribute("aria-expanded", "false");
  if (restoreFocus) filterOwner.focus();
  filterOwner = null;
}

function applyDeviceFilter(name, value) {
  const control = { project_id: projectFilter, state: stateFilter, gpu_state: gpuStateFilter }[name];
  if (control === undefined || control === null) return;
  control.value = value;
  if (name === "project_id") requestedProjectId = value || null;
  resetDevicePagination();
  void reloadDevices();
}

function clearDeviceFilter(name) {
  if (name === "project_id" && projectFilter !== null) {
    projectFilter.value = "";
    requestedProjectId = null;
  }
  if (name === "state" && stateFilter !== null) stateFilter.value = "";
  if (name === "gpu_state" && gpuStateFilter !== null) gpuStateFilter.value = "";
  if (name === "search" && search !== null) search.value = "";
  if (name === "include_disabled" && includeDisabled !== null) includeDisabled.checked = false;
  resetDevicePagination();
  void reloadDevices();
}

function deviceFiltersAreActive() {
  return Boolean(
    projectFilter?.value ||
      requestedProjectId ||
      stateFilter?.value ||
      gpuStateFilter?.value ||
      search?.value.trim() ||
      includeDisabled?.checked
  );
}

function clearDeviceFilters() {
  filters.reset();
  requestedProjectId = null;
  resetDevicePagination();
  void reloadDevices();
}

function openFilterPopover(name, owner) {
  closeFilterPopover({ restoreFocus: false });
  const popover = document.createElement("div");
  popover.className = "filter-popover";
  popover.setAttribute("role", "dialog");
  popover.setAttribute("aria-label", `Filter ${owner.textContent}`);
  filterOwner = owner;
  owner.setAttribute("aria-expanded", "true");
  for (const [value, label] of filterOptions(name)) {
    const option = element("button", displayValue(label));
    option.type = "button";
    option.dataset.filterOption = name;
    option.dataset.filterValue = value;
    popover.append(option);
  }
  popover.addEventListener("keydown", (event) => {
    const options = Array.from(popover.querySelectorAll("button"));
    if (event.key === "Escape") {
      event.preventDefault();
      closeFilterPopover();
      return;
    }
    if (event.key !== "Tab" || options.length === 0) return;
    const index = options.indexOf(document.activeElement);
    if ((!event.shiftKey && index === options.length - 1) || (event.shiftKey && index === 0)) {
      event.preventDefault();
      options[event.shiftKey ? options.length - 1 : 0].focus();
    }
  });
  owner.parentElement.append(popover);
  activeFilterPopover = popover;
  popover.querySelector("button")?.focus();
}

function conciseOsLabel(os) {
  const name = typeof os?.name === "string" ? os.name.trim() : "";
  const version = typeof os?.version === "string" ? os.version.trim() : "";
  if (!name) return "Not reported";
  return version && !name.includes(version) ? `${name} ${version}` : name;
}

function deviceAttention(item) {
  const notices = [];
  if (item.state === "OFFLINE" || item.state === "SUSPECT") {
    notices.push({ label: `Communication: ${item.state}`, kind: "communication" });
  }
  const gpuState = item.gpu_health?.effective;
  if (item.latest_received_at && ["GPU_MISSING", "NVIDIA_SMI_FAILED", "DRIVER_ERROR", "UNKNOWN"].includes(gpuState)) {
    notices.push({ label: `GPU: ${gpuState.replaceAll("_", " ")}`, kind: "gpu" });
  }
  return notices;
}

function deviceRow(item) {
  const row = document.createElement("tr");
  if (item.telemetry_stale === true) row.classList.add("telemetry-stale");
  const notices = deviceAttention(item);
  if (notices.length) row.classList.add("device-row--attention");
  if (notices.some((notice) => notice.kind === "communication")) row.classList.add("device-row--communication");
  const deviceCell = document.createElement("td");
  deviceCell.className = "device-identity";
  const detailButton = element("button", displayValue(item.name));
  detailButton.type = "button";
  detailButton.ariaLabel = `View details for ${displayValue(item.name)}`;
  detailButton.className = "device-identity__name";
  detailButton.addEventListener("click", () => openDetail(item.device_id, detailButton));
  deviceCell.append(detailButton);
  const devicePageLink = element("a", "Open device →");
  devicePageLink.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}`;
  devicePageLink.className = "device-identity__page-link";
  devicePageLink.ariaLabel = `Open device page for ${displayValue(item.name)}`;
  deviceCell.append(devicePageLink);
  if (item.hostname && item.hostname !== item.name && item.hostname !== "unknown") {
    const hostname = element("span", item.hostname);
    hostname.className = "device-identity__hostname";
    deviceCell.append(hostname);
  }
  row.append(deviceCell, element("td", displayValue(item.project?.name)));
  const availability = document.createElement("td");
  availability.append(statusPill(item.state));
  row.append(availability);
  row.append(element("td", conciseOsLabel(item.os)));
  const gpuHealth = document.createElement("td");
  gpuHealth.append(statusPill(item.gpu_health?.effective));
  row.append(gpuHealth);
  const lastSeen = document.createElement("td");
  lastSeen.append(timestampNode(item.last_seen_at));
  row.append(lastSeen);
  const attention = document.createElement("td");
  attention.className = "device-attention";
  for (const notice of notices) {
    const label = element("span", notice.label);
    label.className = `device-attention__item device-attention__item--${notice.kind}`;
    attention.append(label);
  }
  if (!notices.length) attention.append(element("span", "—"));
  row.append(attention);
  return row;
}

function renderDevices(items, { append = false } = {}) {
  const deviceItems = Array.isArray(items) ? items : [];
  const scrollTop = devices.scrollTop;
  let table = append ? document.getElementById("device-status-table") : null;
  if (!append) devices.replaceChildren();
  setVisible(deviceLoading, false);
  if (!deviceItems.length && !append) {
    const noDevices = overviewTotal === 0;
    deviceEmpty.textContent = noDevices
      ? "No devices have been enrolled."
      : "No devices match the current search or filters.";
    setVisible(deviceEmpty, true);
    return;
  }
  if (table === null) {
    table = tableHeader();
    devices.append(table);
  }
  const body = table.tBodies[0];
  for (const item of deviceItems) body.append(deviceRow(item));
  devices.scrollTop = scrollTop;
}

function updateLoadMore() {
  loadMore.disabled = loadingDevices;
  setVisible(loadMore, typeof nextCursor === "string" && nextCursor.length > 0);
  if (previousPage !== null) previousPage.disabled = loadingDevices || pageIndex === 0;
  if (pageContext !== null) pageContext.textContent = `Page ${pageIndex + 1}`;
}

function renderActiveFilters() {
  if (activeFilters === null) return;
  activeFilters.replaceChildren();
  const values = [
    ["Project", projectFilter?.selectedOptions[0]?.textContent, "project_id"],
    ["Availability", stateFilter?.value, "state"],
    ["GPU Health", gpuStateFilter?.value, "gpu_state"],
    ["Search", search?.value.trim(), "search"],
    ["Disabled devices", includeDisabled?.checked ? "Included" : "", "include_disabled"],
  ];
  for (const [label, value, name] of values) {
    if (!value || value === "All projects") continue;
    const chip = element("button", `${label}: ${value} ×`);
    chip.type = "button";
    chip.ariaLabel = `Remove ${label} filter`;
    chip.addEventListener("click", () => {
      clearDeviceFilter(name);
    });
    activeFilters.append(chip);
  }
  setVisible(resetFilters, deviceFiltersAreActive());
}

function showDeviceError() {
  deviceError.textContent = "Unable to refresh the device list. Displayed device data was retained.";
  setVisible(deviceError, true);
}

function markDashboardStale() {
  const lastUpdated = lastSuccessfulRefresh === null ? "not yet available" : formatRelativeTime(lastSuccessfulRefresh);
  staleWarning.textContent = `Data stale - last updated ${lastUpdated}.`;
  setVisible(staleWarning, true);
}

function markDashboardFresh(serverTime) {
  lastSuccessfulRefresh = serverTime;
  lastRefresh.textContent = `Last successful refresh: ${formatRelativeTime(serverTime)}.`;
  setExactTimestamp(lastRefresh, serverTime);
  setVisible(staleWarning, false);
}

function applyDevicePayload(payload, { append = false } = {}) {
  clearDeviceMessages();
  renderDevices(payload.items, { append });
  nextCursor = typeof payload.next_cursor === "string" ? payload.next_cursor : null;
  updateLoadMore();
  renderActiveFilters();
  if (devicesResultContext !== null) {
    const count = Array.isArray(payload.items) ? payload.items.length : 0;
    devicesResultContext.textContent = `Showing ${count} device${count === 1 ? "" : "s"} on this page${deviceFiltersAreActive() ? " for the current search or filters." : "."}`;
  }
  refreshStatus.textContent = `Device list updated ${displayValue(payload.server_time)}`;
}

async function reloadDevices() {
  if (refreshing || loadingDevices) return;
  loadingDevices = true;
  resetDevicePagination();
  clearDeviceMessages();
  setVisible(deviceLoading, true);
  updateLoadMore();
  refreshStatus.textContent = "Loading current device status…";
  try {
    const [devicesResult, overviewResult] = await Promise.allSettled([
      requestDevices(currentCursor()),
      requestOverview(),
    ]);
    if (devicesResult.status === "fulfilled") applyDevicePayload(devicesResult.value);
    else showDeviceError();
    if (overviewResult.status === "fulfilled") renderDeviceWorkspaceSummary(overviewResult.value);
    else showDeviceWorkspaceSummaryError();
    if (devicesResult.status !== "fulfilled" || overviewResult.status !== "fulfilled") markDashboardStale();
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    setVisible(deviceLoading, false);
    updateLoadMore();
  }
}

async function nextDevicePage() {
  if (refreshing || loadingDevices || !nextCursor) return;
  cursorHistory = cursorHistory.slice(0, pageIndex + 1);
  cursorHistory.push(nextCursor);
  pageIndex += 1;
  loadingDevices = true;
  setVisible(deviceLoading, true);
  updateLoadMore();
  try {
    applyDevicePayload(await requestDevices(currentCursor()));
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    setVisible(deviceLoading, false);
    updateLoadMore();
  }
}

async function previousDevicePage() {
  if (loadingDevices || pageIndex === 0) return;
  pageIndex -= 1;
  loadingDevices = true;
  setVisible(deviceLoading, true);
  try {
    applyDevicePayload(await requestDevices(currentCursor()));
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    setVisible(deviceLoading, false);
    updateLoadMore();
  }
}

function scheduleRefresh() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(refreshActiveView, document.hidden ? 60000 : 15000);
}

async function refreshDashboard() {
  if (refreshing || loadingDevices) {
    if (!refreshing) scheduleRefresh();
    return;
  }
  refreshing = true;
  const refreshCursor = currentCursor();
  const refreshPageIndex = pageIndex;
  refreshStatus.textContent = "Refreshing dashboard…";
  try {
    const [projectsResult, devicesResult, overviewResult] = await Promise.allSettled([
      requestProjects(),
      requestDevices(refreshCursor),
      requestOverview(),
    ]);
    const projectsSucceeded = projectsResult.status === "fulfilled";
    const devicesSucceeded = devicesResult.status === "fulfilled";
    if (projectsSucceeded) renderProjects(projectsResult.value.items, false);
    if (overviewResult.status === "fulfilled") renderDeviceWorkspaceSummary(overviewResult.value);
    else showDeviceWorkspaceSummaryError();
    if (devicesSucceeded && currentCursor() === refreshCursor && pageIndex === refreshPageIndex) {
      applyDevicePayload(devicesResult.value);
    }
    else showDeviceError();
    if (projectsSucceeded && devicesSucceeded && overviewResult.status === "fulfilled") {
      markDashboardFresh(devicesResult.value.server_time);
      await refreshOpenDetail();
    } else markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

async function refreshOverviewView() {
  if (refreshing) return;
  refreshing = true;
  try {
    const [overviewResult, incidentsResult] = await Promise.allSettled([
      requestOverview(),
      requestRecentIncidents(),
    ]);
    if (overviewResult.status === "fulfilled") renderOverview(overviewResult.value);
    if (incidentsResult.status === "fulfilled") renderRecentIncidents(incidentsResult.value.items);
    if (overviewResult.status !== "fulfilled" || incidentsResult.status !== "fulfilled") {
      if (overviewResult.status !== "fulfilled") {
        if (overviewLoading !== null) overviewLoading.hidden = true;
        if (overviewError !== null) {
          overviewError.textContent = "Overview data could not be loaded. Existing data may be stale.";
          overviewError.hidden = false;
        }
      } else if (overviewError !== null) {
        overviewError.textContent = "Recent incident data could not be loaded. Overview data remains current.";
        overviewError.hidden = false;
      }
      markDashboardStale();
      return;
    }
    markDashboardFresh(overviewResult.value.server_time);
    await refreshOpenDetail();
  } catch (_) {
    if (overviewLoading !== null) overviewLoading.hidden = true;
    if (overviewError !== null) {
      overviewError.textContent = "Overview data could not be loaded. Existing data may be stale.";
      overviewError.hidden = false;
    }
    markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

async function refreshProjectsView() {
  if (refreshing) return;
  refreshing = true;
  try {
    const result = await requestProjects();
    renderProjects(result.items, false);
    markDashboardFresh(result.server_time);
  } catch (_) {
    markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

function canEditUser(user) {
  if (user.role === "OWNER") return false;
  return dashboardRole === "OWNER" || (dashboardRole === "ADMIN" && user.role === "USER");
}

function renderUsers(items) {
  usersTableBody.replaceChildren();
  for (const user of items) {
    const row = document.createElement("tr");
    row.append(
      element("td", user.name || "—"),
      element("td", user.email),
      (() => { const cell = document.createElement("td"); cell.append(statusPill(user.role)); return cell; })(),
      (() => { const cell = document.createElement("td"); cell.append(statusPill(user.active ? "ACTIVE" : "DISABLED")); return cell; })(),
      (() => { const cell = document.createElement("td"); cell.append(timestampNode(user.created_at)); return cell; })(),
      (() => { const cell = document.createElement("td"); cell.append(timestampNode(user.updated_at)); return cell; })(),
    );
    const action = document.createElement("td");
    if (canEditUser(user)) {
      const button = element("button", "Edit");
      button.type = "button";
      button.className = "sb-button--secondary";
      button.addEventListener("click", () => openUserDialog(user));
      action.append(button);
    } else {
      action.textContent = "—";
    }
    row.append(action);
    usersTableBody.append(row);
  }
  setVisible(usersEmpty, items.length === 0);
}

async function refreshUsersView() {
  if (refreshing) return;
  refreshing = true;
  try {
    const result = await requestUsers();
    renderUsers(result.items);
    usersStatus.textContent = `${result.items.length} provisioned user${result.items.length === 1 ? "" : "s"}.`;
    markDashboardFresh(null);
  } catch (_) {
    usersStatus.textContent = "Users could not be loaded. Existing data may be stale.";
    markDashboardStale();
  } finally {
    refreshing = false;
  }
}

const ALERT_ROUTING_EVENTS = [
  ["device_offline_enabled", "Device offline", "Device stops reporting to SkyBeat."],
  ["device_recovered_enabled", "Device recovered", "Communication resumes after an offline incident."],
  ["gpu_degraded_enabled", "GPU degraded", "SkyBeat detects confirmed GPU degradation."],
  ["gpu_recovered_enabled", "GPU recovered", "GPU health returns to normal."],
];

function notificationEventControl(name, label, description, checked) {
  const control = document.createElement("label");
  control.className = "alert-routing-event";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.name = name;
  input.checked = checked;
  const copy = document.createElement("span");
  copy.className = "alert-routing-event__copy";
  copy.append(element("strong", label), element("span", description));
  control.append(copy, input);
  return [control, input];
}

function notificationPolicy(project) {
  return {
    recipients: [...project.recipients].sort(),
    device_offline_enabled: project.device_offline_enabled,
    device_recovered_enabled: project.device_recovered_enabled,
    gpu_degraded_enabled: project.gpu_degraded_enabled,
    gpu_recovered_enabled: project.gpu_recovered_enabled,
  };
}

function notificationDraftFor(project) {
  if (notificationDraft?.projectId !== project.project_id) {
    const saved = notificationPolicy(project);
    notificationDraft = {
      projectId: project.project_id,
      saved,
      recipients: new Set(saved.recipients),
      device_offline_enabled: saved.device_offline_enabled,
      device_recovered_enabled: saved.device_recovered_enabled,
      gpu_degraded_enabled: saved.gpu_degraded_enabled,
      gpu_recovered_enabled: saved.gpu_recovered_enabled,
    };
  }
  return notificationDraft;
}

function notificationDraftPayload(draft) {
  return {
    recipients: [...draft.recipients].sort(),
    device_offline_enabled: draft.device_offline_enabled,
    device_recovered_enabled: draft.device_recovered_enabled,
    gpu_degraded_enabled: draft.gpu_degraded_enabled,
    gpu_recovered_enabled: draft.gpu_recovered_enabled,
  };
}

function notificationDraftIsDirty(draft) {
  return JSON.stringify(notificationDraftPayload(draft)) !== JSON.stringify(draft.saved);
}

function selectedNotificationProject() {
  return notificationProjects.find((project) => project.project_id === selectedNotificationProjectId);
}

function notificationUser(email) {
  return notificationUsers.find((user) => user.email === email);
}

function markNotificationDraftUnsaved() {
  const project = selectedNotificationProject();
  if (!project) return;
  const draft = notificationDraftFor(project);
  notificationSaveState = notificationDraftIsDirty(draft) ? "unsaved" : "unchanged";
  notificationSaveMessage =
    notificationSaveState === "unsaved" ? "Unsaved changes" : "No changes.";
  renderNotificationProjects();
}

function renderRecipientChips(
  container, project, draft,
  onChange = markNotificationDraftUnsaved,
  emptyDescription = null,
) {
  container.replaceChildren();
  if (draft.recipients.size === 0) {
    const empty = element("p", "No recipients assigned");
    empty.className = "recipient-assignment-empty";
    const explanation = element(
      "p",
      emptyDescription ?? (project.configured
        ? "Alerts for this configured project policy will not have project recipients."
        : "No project recipients are configured. The existing fallback remains active until you save this project policy."),
    );
    explanation.className = "recipient-assignment-empty__detail";
    container.append(empty, explanation);
    return;
  }
  for (const address of [...draft.recipients].sort()) {
    const user = notificationUser(address);
    const recipientChip = document.createElement("div");
    recipientChip.className = "recipient-assignment";
    const identity = document.createElement("span");
    identity.className = "recipient-assignment__identity";
    identity.append(
      element("strong", user?.name || "Email recipient"),
      element("span", address),
    );
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "recipient-chip__remove";
    remove.textContent = "×";
    remove.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight;
    remove.setAttribute("aria-label", `Remove ${user?.name || address}`);
    remove.addEventListener("click", () => {
      draft.recipients.delete(address);
      onChange();
    });
    recipientChip.append(identity, remove);
    container.append(recipientChip);
  }
}

function notificationDeviceDraftFor(device) {
  if (notificationDeviceDraft?.deviceId !== device.device_id) {
    const saved = device.custom ?? device.inherited;
    notificationDeviceDraft = {
      deviceId: device.device_id,
      savedMode: device.mode,
      mode: device.mode,
      saved: { ...saved, recipients: [...saved.recipients].sort() },
      recipients: new Set(saved.recipients),
      device_offline_enabled: saved.device_offline_enabled,
      device_recovered_enabled: saved.device_recovered_enabled,
      gpu_degraded_enabled: saved.gpu_degraded_enabled,
      gpu_recovered_enabled: saved.gpu_recovered_enabled,
    };
  }
  return notificationDeviceDraft;
}

function notificationDeviceDraftIsDirty(draft) {
  return draft.mode !== draft.savedMode ||
    (draft.mode === "CUSTOM" &&
      JSON.stringify(notificationDraftPayload(draft)) !== JSON.stringify(draft.saved));
}

function markNotificationDeviceUnsaved() {
  const device = notificationDevices.find((item) => item.device_id === selectedNotificationDeviceId);
  if (!device) return;
  notificationDeviceSaveState = notificationDeviceDraftIsDirty(notificationDeviceDraftFor(device))
    ? "unsaved" : "unchanged";
  notificationDeviceSaveMessage = notificationDeviceSaveState === "unsaved"
    ? "Unsaved changes" : "No changes.";
  renderNotificationProjects();
}

function notificationRoutingSummary(mode, policy) {
  const count = policy.recipients.length;
  const recipients = count === 0 ? "No recipients" : `${count} recipient${count === 1 ? "" : "s"}`;
  const events = ALERT_ROUTING_EVENTS.filter(([name]) => policy[name]).map(([, label]) => label);
  return `${mode === "CUSTOM" ? "Custom" : "Inherits"} · ${recipients} · ${events.length ? events.join(" + ") : "No alert types enabled"}`;
}

function renderNotificationEffective(container, policy) {
  const addresses = document.createElement("div");
  addresses.className = "recipient-chip-list";
  if (policy.recipients.length === 0) {
    addresses.append(element("p", "No recipients"));
  } else {
    for (const address of policy.recipients) {
      const user = notificationUser(address);
      const chip = document.createElement("div");
      chip.className = "recipient-assignment";
      const identity = document.createElement("span");
      identity.className = "recipient-assignment__identity";
      identity.append(element("strong", user?.name || "Email recipient"), element("span", address));
      chip.append(identity);
      addresses.append(chip);
    }
  }
  const events = document.createElement("div");
  events.className = "alert-routing-events";
  for (const [name, label, description] of ALERT_ROUTING_EVENTS) {
    const [control, input] = notificationEventControl(name, label, description, policy[name]);
    input.disabled = true;
    events.append(control);
  }
  container.append(element("h4", "Effective recipients"), addresses, element("h4", "Alert types"), events);
}

async function loadNotificationDevices(projectId) {
  const requestId = ++notificationDeviceRequestId;
  notificationDeviceLoadState = "loading";
  renderNotificationProjects();
  try {
    const result = await requestNotificationDevices(projectId);
    if (requestId !== notificationDeviceRequestId || selectedNotificationProjectId !== projectId) return;
    notificationDevices = result.items;
    if (!notificationDevices.some((item) => item.device_id === selectedNotificationDeviceId)) {
      selectedNotificationDeviceId = notificationDevices[0]?.device_id ?? null;
    }
    notificationDeviceDraft = null;
    notificationDeviceLoadState = "ready";
  } catch (_) {
    if (requestId !== notificationDeviceRequestId || selectedNotificationProjectId !== projectId) return;
    notificationDeviceLoadState = "failed";
  }
  renderNotificationProjects();
}

function renderNotificationDevices() {
  const project = selectedNotificationProject();
  if (!project) return;
  const section = document.createElement("section");
  section.className = "alert-routing-device sb-card";
  section.append(element("h3", "Device overrides"),
    element("p", "Devices inherit project routing until you save a custom policy for one device."));
  if (notificationDeviceLoadState === "loading") {
    section.append(element("p", "Loading devices…"));
    notificationsList.append(section);
    return;
  }
  if (notificationDeviceLoadState === "failed") {
    const retry = element("button", "Retry loading devices");
    retry.type = "button";
    retry.className = "sb-button--secondary";
    retry.addEventListener("click", () => loadNotificationDevices(project.project_id));
    section.append(element("p", "Device routing could not be loaded."), retry);
    notificationsList.append(section);
    return;
  }
  if (notificationDevices.length === 0) {
    section.append(element("p", "No devices belong to this project."));
    notificationsList.append(section);
    return;
  }
  const layout = document.createElement("div");
  layout.className = "alert-routing-device__layout";
  const list = document.createElement("div");
  list.id = "device-routing-list";
  list.className = "alert-routing-device__list";
  list.setAttribute("aria-label", "Devices in this project");
  for (const device of notificationDevices) {
    const row = element("button", "");
    row.type = "button";
    row.className = "alert-routing-device__row";
    row.setAttribute("aria-pressed", device.device_id === selectedNotificationDeviceId ? "true" : "false");
    const badge = element("span", device.mode === "CUSTOM" ? "CUSTOM ROUTING" : "INHERITS PROJECT");
    badge.className = `status-pill alert-routing-device__badge alert-routing-device__badge--${device.mode.toLowerCase()}`;
    row.append(element("strong", device.device_name), badge,
      element("span", notificationRoutingSummary(device.mode, device.effective)));
    row.addEventListener("click", () => {
      if (device.device_id === selectedNotificationDeviceId || notificationDeviceSaveInFlight) return;
      const current = notificationDevices.find((item) => item.device_id === selectedNotificationDeviceId);
      if (current && notificationDeviceDraftIsDirty(notificationDeviceDraftFor(current))) {
        notificationDeviceSaveState = "unsaved";
        notificationDeviceSaveMessage = "Save or discard device changes before switching devices.";
        renderNotificationProjects();
        return;
      }
      selectedNotificationDeviceId = device.device_id;
      notificationDeviceDraft = null;
      notificationDeviceSaveState = "unchanged";
      notificationDeviceSaveMessage = "No changes.";
      renderNotificationProjects();
    });
    list.append(row);
  }
  layout.append(list);
  const device = notificationDevices.find((item) => item.device_id === selectedNotificationDeviceId);
  if (!device) return;
  const draft = notificationDeviceDraftFor(device);
  const editor = document.createElement("div");
  editor.className = "alert-routing-device__editor";
  editor.append(element("h4", device.device_name), element("p", `Project: ${device.project_name}`));
  const mode = document.createElement("fieldset");
  mode.className = "alert-routing-device__mode";
  mode.append(element("legend", "Routing"));
  for (const [value, label] of [["INHERIT_PROJECT", "Inherit project"], ["CUSTOM", "Custom routing"]]) {
    const option = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "device-routing-mode";
    input.value = value;
    input.checked = draft.mode === value;
    input.disabled = notificationDeviceSaveInFlight;
    input.addEventListener("change", () => {
      if (value === draft.mode) return;
      if (notificationDeviceDraftIsDirty(draft) && draft.mode === "CUSTOM") {
        notificationDeviceSaveState = "unsaved";
        notificationDeviceSaveMessage = "Save or discard device changes before switching routing mode.";
        renderNotificationProjects();
        return;
      }
      draft.mode = value;
      markNotificationDeviceUnsaved();
    });
    option.append(input, element("span", label));
    mode.append(option);
  }
  editor.append(mode);
  if (draft.mode === "INHERIT_PROJECT") {
    editor.append(element("p", device.mode === "CUSTOM"
      ? `This device will use ${device.project_name} routing after you select Use project routing.`
      : `This device currently uses ${device.project_name} routing.`));
    renderNotificationEffective(editor, device.inherited);
  } else {
    const recipientsSection = document.createElement("section");
    recipientsSection.className = "alert-routing-section";
    recipientsSection.append(element("h4", "Recipients"),
      element("p", "Assign active SkyBeat users for this device override."));
    const chips = document.createElement("div");
    renderRecipientChips(chips, project, draft, markNotificationDeviceUnsaved,
      "No email will be sent for this device while this override has no recipients.");
    const controls = document.createElement("div");
    controls.className = "recipient-assignment-controls";
    const select = document.createElement("select");
    select.id = "device-notification-recipient-select";
    select.setAttribute("aria-label", "Assign an active SkyBeat user to this device");
    const available = notificationUsers.filter((user) => user.active && !draft.recipients.has(user.email));
    const placeholder = element("option", notificationDirectoryAvailable
      ? "Choose an active SkyBeat user" : "Active user directory is unavailable");
    placeholder.value = "";
    select.append(placeholder);
    for (const user of available) {
      const option = element("option", `${user.name || user.email} — ${user.email}`);
      option.value = user.email;
      select.append(option);
    }
    select.disabled = notificationDeviceSaveInFlight || !notificationDirectoryAvailable || available.length === 0;
    const assign = element("button", "Assign device recipient");
    assign.type = "button";
    assign.className = "sb-button--secondary";
    assign.disabled = select.disabled;
    assign.addEventListener("click", () => {
      if (!select.value) return;
      draft.recipients.add(select.value);
      markNotificationDeviceUnsaved();
    });
    controls.append(select, assign);
    if (!notificationDirectoryAvailable) {
      controls.append(element("p", "The active user directory is unavailable. Existing recipients remain visible."));
    }
    recipientsSection.append(chips, controls);
    const events = document.createElement("section");
    events.className = "alert-routing-section";
    events.append(element("h4", "Alert types"));
    const eventControls = document.createElement("div");
    eventControls.className = "alert-routing-events";
    for (const [name, label, description] of ALERT_ROUTING_EVENTS) {
      const [control, input] = notificationEventControl(name, label, description, draft[name]);
      input.disabled = notificationDeviceSaveInFlight;
      input.addEventListener("change", () => {
        draft[name] = input.checked;
        markNotificationDeviceUnsaved();
      });
      eventControls.append(control);
    }
    events.append(eventControls);
    editor.append(recipientsSection, events);
  }
  const actions = document.createElement("div");
  actions.className = "alert-routing-device__actions";
  if (draft.mode === "CUSTOM") {
    const save = element("button", "Save device routing");
    save.type = "button";
    save.className = "sb-button--primary";
    save.disabled = notificationDeviceSaveInFlight || !notificationDeviceDraftIsDirty(draft);
    save.addEventListener("click", async () => {
      if (notificationDeviceSaveInFlight) return;
      if (notificationDraftIsDirty(notificationDraftFor(project))) {
        notificationDeviceSaveState = "unsaved";
        notificationDeviceSaveMessage = "Save or discard project changes before saving device routing.";
        renderNotificationProjects();
        return;
      }
      notificationDeviceSaveInFlight = true;
      notificationDeviceSaveState = "saving";
      notificationDeviceSaveMessage = "Saving";
      renderNotificationProjects();
      try {
        await requestDashboardMutation(
          `/api/v1/notifications/${encodeURIComponent(project.project_id)}/devices/${encodeURIComponent(device.device_id)}`,
          "PUT", notificationDraftPayload(draft),
        );
        const result = await requestNotificationDevices(project.project_id);
        notificationDevices = result.items;
        notificationDeviceDraft = null;
        notificationDeviceSaveState = "saved";
        notificationDeviceSaveMessage = "Saved";
      } catch (_) {
        notificationDeviceSaveState = "failed";
        notificationDeviceSaveMessage = "Save failed. Your unsaved changes are still shown.";
      } finally {
        notificationDeviceSaveInFlight = false;
        renderNotificationProjects();
      }
    });
    actions.append(save);
  }
  const discard = element("button", "Discard device changes");
  discard.type = "button";
  discard.className = "sb-button--ghost";
  discard.disabled = notificationDeviceSaveInFlight || !notificationDeviceDraftIsDirty(draft);
  discard.addEventListener("click", () => {
    notificationDeviceDraft = null;
    notificationDeviceSaveState = "unchanged";
    notificationDeviceSaveMessage = "Changes discarded.";
    renderNotificationProjects();
  });
  actions.append(discard);
  if (device.mode === "CUSTOM") {
    const reset = element("button", "Use project routing");
    reset.type = "button";
    reset.className = "sb-button--secondary";
    reset.disabled = notificationDeviceSaveInFlight ||
      (draft.mode === "CUSTOM" && notificationDeviceDraftIsDirty(draft));
    reset.addEventListener("click", async () => {
      if (notificationDraftIsDirty(notificationDraftFor(project))) {
        notificationDeviceSaveState = "unsaved";
        notificationDeviceSaveMessage = "Save or discard project changes before resetting device routing.";
        renderNotificationProjects();
        return;
      }
      notificationDeviceSaveInFlight = true;
      notificationDeviceSaveState = "saving";
      notificationDeviceSaveMessage = "Saving";
      renderNotificationProjects();
      try {
        await requestDashboardMutation(
          `/api/v1/notifications/${encodeURIComponent(project.project_id)}/devices/${encodeURIComponent(device.device_id)}`,
          "DELETE", null,
        );
        const result = await requestNotificationDevices(project.project_id);
        notificationDevices = result.items;
        notificationDeviceDraft = null;
        notificationDeviceSaveState = "saved";
        notificationDeviceSaveMessage = "Saved";
      } catch (_) {
        notificationDeviceSaveState = "failed";
        notificationDeviceSaveMessage = "Reset failed. Your device draft is still shown.";
      } finally {
        notificationDeviceSaveInFlight = false;
        renderNotificationProjects();
      }
    });
    actions.append(reset);
  }
  const status = element("p", notificationDeviceSaveMessage);
  status.className = `alert-routing-save-status alert-routing-save-status--${notificationDeviceSaveState}`;
  status.setAttribute("aria-live", "polite");
  editor.append(actions, status);
  layout.append(editor);
  section.append(layout);
  notificationsList.append(section);
}

function replaceNotificationProjects(items) {
  notificationProjects = items;
  if (
    !selectedNotificationProjectId ||
    !notificationProjects.some((project) => project.project_id === selectedNotificationProjectId)
  ) {
    selectedNotificationProjectId = notificationProjects[0]?.project_id ?? null;
  }
  notificationDraft = null;
}

function renderNotificationProjects() {
  notificationsList.replaceChildren();
  if (!selectedNotificationProjectId) {
    notificationsList.append(element("p", "No projects are available for alert routing."));
    return;
  }
  const project = selectedNotificationProject();
  if (!project) return;
  const draft = notificationDraftFor(project);

  const card = document.createElement("article");
  card.className = "alert-routing-card sb-card";
  card.append(element("h3", "Project routing"));
  const projectField = document.createElement("label");
  projectField.className = "alert-routing-project";
  projectField.append(element("span", "Project"));
  const projectSelect = document.createElement("select");
  projectSelect.id = "notification-project-select";
  projectSelect.setAttribute("aria-label", "Project alert routing policy");
  for (const item of notificationProjects) {
    const option = element("option", item.project_name);
    option.value = item.project_id;
    option.selected = item.project_id === project.project_id;
    projectSelect.append(option);
  }
  projectSelect.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight;
  projectSelect.addEventListener("change", async () => {
    if (projectSelect.value === selectedNotificationProjectId) return;
    if (notificationDraftIsDirty(draft)) {
      notificationSaveState = "unsaved";
      notificationSaveMessage = "Unsaved changes";
      renderNotificationProjects();
      return;
    }
    const currentDevice = notificationDevices.find((item) => item.device_id === selectedNotificationDeviceId);
    if (currentDevice && notificationDeviceDraftIsDirty(notificationDeviceDraftFor(currentDevice))) {
      notificationDeviceSaveState = "unsaved";
      notificationDeviceSaveMessage = "Save or discard device changes before switching projects.";
      renderNotificationProjects();
      return;
    }
    selectedNotificationProjectId = projectSelect.value;
    notificationDraft = null;
    notificationDevices = [];
    selectedNotificationDeviceId = null;
    notificationDeviceDraft = null;
    notificationDeviceLoadState = "loading";
    notificationSaveState = "unchanged";
    notificationSaveMessage = "No changes.";
    notificationDeviceSaveState = "unchanged";
    notificationDeviceSaveMessage = "No changes.";
    renderNotificationProjects();
    await loadNotificationDevices(selectedNotificationProjectId);
  });
  projectField.append(projectSelect);

  const policyState = document.createElement("section");
  policyState.className = "alert-routing-policy-state";
  const badge = element("span", project.configured ? "Custom routing" : "Using fallback routing");
  badge.className = `status-pill ${project.configured ? "status-ok" : "status-active"}`;
  const stateCopy = element(
    "p",
    project.configured
      ? "This project uses its own recipients and alert settings."
      : "This project currently uses the deployment-wide recipients and alert settings. Saving changes creates a project-specific routing policy.",
  );
  policyState.append(badge, stateCopy);

  const recipientsSection = document.createElement("section");
  recipientsSection.className = "alert-routing-section";
  recipientsSection.append(
    element("h3", "Recipients"),
    element("p", "Assign active SkyBeat users to receive alerts for this project."),
  );
  const chipList = document.createElement("div");
  chipList.className = "recipient-chip-list";
  chipList.setAttribute("aria-label", "Selected alert recipients");
  renderRecipientChips(chipList, project, draft);
  const assignmentControls = document.createElement("div");
  assignmentControls.className = "recipient-assignment-controls";
  const recipientSelect = document.createElement("select");
  recipientSelect.id = "notification-recipient-select";
  recipientSelect.setAttribute("aria-label", "Assign an active SkyBeat user");
  const eligibleUsers = notificationUsers.filter(
    (user) => user.active && !draft.recipients.has(user.email),
  );
  const placeholder = element(
    "option",
    notificationDirectoryAvailable
      ? "Choose an active SkyBeat user"
      : "Active user directory is unavailable",
  );
  placeholder.value = "";
  placeholder.selected = true;
  recipientSelect.append(placeholder);
  for (const user of eligibleUsers) {
    const option = element("option", `${user.name || user.email} — ${user.email}`);
    option.value = user.email;
    recipientSelect.append(option);
  }
  recipientSelect.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight ||
    !notificationDirectoryAvailable || eligibleUsers.length === 0;
  const assignRecipient = element("button", "Assign recipient");
  assignRecipient.type = "button";
  assignRecipient.className = "sb-button--secondary";
  assignRecipient.disabled = recipientSelect.disabled;
  assignRecipient.addEventListener("click", () => {
    if (!recipientSelect.value) return;
    draft.recipients.add(recipientSelect.value);
    markNotificationDraftUnsaved();
  });
  assignmentControls.append(recipientSelect, assignRecipient);
  if (!notificationDirectoryAvailable) {
    assignmentControls.append(
      element("p", "The active user directory could not be loaded. Existing recipients remain visible."),
    );
  }
  recipientsSection.append(chipList, assignmentControls);

  const eventSection = document.createElement("section");
  eventSection.className = "alert-routing-section";
  eventSection.append(
    element("h3", "Alert types"),
    element("p", "Choose which events generate notifications."),
  );
  const eventControls = document.createElement("div");
  eventControls.className = "alert-routing-events";
  for (const [name, label, description] of ALERT_ROUTING_EVENTS) {
    const [control, input] = notificationEventControl(name, label, description, draft[name]);
    input.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight;
    input.addEventListener("change", () => {
      draft[name] = input.checked;
      markNotificationDraftUnsaved();
    });
    eventControls.append(control);
  }
  eventSection.append(eventControls);

  const save = element("button", "Save routing policy");
  save.type = "button";
  save.className = "sb-button--primary";
  save.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight;
  save.addEventListener("click", async () => {
    if (notificationSaveInFlight || notificationDeviceSaveInFlight) return;
    const currentDevice = notificationDevices.find((item) => item.device_id === selectedNotificationDeviceId);
    if (currentDevice && notificationDeviceDraftIsDirty(notificationDeviceDraftFor(currentDevice))) {
      notificationSaveState = "unsaved";
      notificationSaveMessage = "Save or discard device changes before saving project routing.";
      renderNotificationProjects();
      return;
    }
    if (!notificationDraftIsDirty(draft)) {
      notificationSaveState = "unchanged";
      notificationSaveMessage = "No changes.";
      renderNotificationProjects();
      return;
    }
    notificationSaveInFlight = true;
    notificationSaveState = "saving";
    notificationSaveMessage = "Saving";
    renderNotificationProjects();
    try {
      await requestDashboardMutation(
        `/api/v1/notifications/${encodeURIComponent(project.project_id)}`,
        "PUT",
        notificationDraftPayload(draft),
      );
      const reloaded = await requestNotifications();
      notificationSaveInFlight = false;
      replaceNotificationProjects(reloaded.items);
      notificationSaveState = "saved";
      notificationSaveMessage = "Saved";
      renderNotificationProjects();
      await loadNotificationDevices(project.project_id);
    } catch (_) {
      notificationSaveInFlight = false;
      notificationSaveState = "failed";
      notificationSaveMessage = "Save failed. Your unsaved changes are still shown.";
      renderNotificationProjects();
    }
  });
  const discard = element("button", "Discard changes");
  discard.type = "button";
  discard.className = "sb-button--ghost";
  discard.disabled = notificationSaveInFlight || notificationDeviceSaveInFlight ||
    !notificationDraftIsDirty(draft);
  discard.addEventListener("click", () => {
    notificationDraft = null;
    notificationSaveState = "unchanged";
    notificationSaveMessage = "Changes discarded.";
    renderNotificationProjects();
  });
  const status = element("p", notificationSaveMessage);
  status.className = `alert-routing-save-status alert-routing-save-status--${notificationSaveState}`;
  status.setAttribute("aria-live", "polite");
  card.append(projectField, policyState, recipientsSection, eventSection, save, discard, status);
  notificationsList.append(card);
  renderNotificationDevices();
}

async function refreshNotificationsView() {
  if (refreshing) return;
  refreshing = true;
  try {
    const result = await requestNotifications();
    try {
      const users = await requestUsers();
      notificationUsers = users.items;
      notificationDirectoryAvailable = true;
    } catch (_) {
      notificationUsers = [];
      notificationDirectoryAvailable = false;
    }
    replaceNotificationProjects(result.items);
    renderNotificationProjects();
    if (selectedNotificationProjectId) await loadNotificationDevices(selectedNotificationProjectId);
    notificationsStatus.textContent = `${result.items.length} project${result.items.length === 1 ? "" : "s"} available for alert routing.`;
    markDashboardFresh(null);
  } catch (_) {
    notificationsStatus.textContent = "Notification policies could not be loaded.";
    markDashboardStale();
  } finally {
    refreshing = false;
  }
}

function deploymentStateLabel(state) {
  return { PENDING: "READY", EXPIRED: "TOKEN EXPIRED", REVOKED: "REVOKED" }[state] ?? "UNAVAILABLE";
}

function deploymentDeleteIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M4 7h16M10 11v6M14 11v6M9 7l1-3h4l1 3M6 7l1 13h10l1-13");
  icon.append(path);
  return icon;
}

function renderDeployments() {
  deploymentsList.replaceChildren();
  deploymentsEmpty.hidden = toInstallDeployments.length !== 0;
  for (const deployment of toInstallDeployments) {
    const card = document.createElement("article");
    card.className = "deployment-card";
    const heading = document.createElement("div");
    heading.className = "deployment-card__header";
    const identity = document.createElement("div");
    identity.append(element("h3", deployment.device_name), element("p", deployment.project_name));
    const cardHeaderActions = document.createElement("div");
    cardHeaderActions.className = "deployment-card__header-actions";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "sb-button--ghost sb-button--icon deployment-card__delete";
    remove.setAttribute("aria-label", `Delete prepared device ${deployment.device_name}`);
    remove.title = "Delete prepared device";
    remove.append(deploymentDeleteIcon());
    remove.addEventListener("click", () => openDeploymentDeleteDialog(deployment));
    cardHeaderActions.append(statusPill(deploymentStateLabel(deployment.state)), remove);
    heading.append(identity, cardHeaderActions);
    const selectedRelease = deploymentRelease;
    const version = element("p", `Agent version: ${selectedRelease === null ? "Not available" : `v${selectedRelease.version}`}`);
    version.className = "deployment-card__version";
    const actions = document.createElement("div");
    actions.className = "deployment-card__actions";
    const isReady = deployment.state === "PENDING";
    const download = element("button", "Agent Package");
    download.type = "button";
    download.className = "sb-button--primary";
    download.disabled = !isReady || deploymentRelease === null;
    download.title = !isReady ? "Enrollment token is not ready." : selectedRelease === null ? "Open Release Management to activate a verified release." : "Download the approved archive shown on this card.";
    download.addEventListener("click", () => window.location.assign(`/api/v1/agent-releases/current/download?archive_sha256=${selectedRelease.archive_sha256}`));
    const copyInstructions = element("button", "Copy Instruction");
    copyInstructions.type = "button";
    copyInstructions.className = "sb-button--secondary";
    copyInstructions.disabled = !isReady || deploymentRelease === null;
    copyInstructions.title = download.title;
    copyInstructions.addEventListener("click", () => navigator.clipboard.writeText(installationInstructions(selectedRelease)).catch(() => { deploymentsStatus.textContent = "Installation instructions could not be copied."; }));
    actions.append(download, copyInstructions);
    card.append(heading, version, actions);
    deploymentsList.append(card);
  }
}

async function requestRegisteredReleases() {
  const response = await fetch("/api/v1/agent-releases", { credentials: "same-origin" });
  if (!response.ok) throw new Error("release registry unavailable");
  const payload = await response.json();
  if (!Array.isArray(payload?.releases) || typeof payload?.storage_status !== "string") throw new Error("release registry response invalid");
  return payload;
}

function renderRegisteredReleases(releases) {
  releaseList.replaceChildren();
  for (const release of releases) {
    if (typeof release.archive_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(release.archive_sha256)) continue;
    const card = document.createElement("article");
    card.append(element("h3", release.version ?? "Unknown version"));
    card.append(element("p", `Archive SHA-256: ${release.archive_sha256}`));
    card.append(element("p", `Wheel SHA-256: ${release.wheel_sha256 ?? "Unavailable"}`));
    card.append(element("p", `Status: ${release.status ?? "Unknown"}${release.active ? " · Active for new installations" : ""} · ${release.available ? "Artifact available" : release.availability_error ?? "Artifact missing or invalid"}`));
    card.append(element("p", `Registered: ${release.registered_at ?? "Unknown"} by ${release.registered_by ?? "Unknown"}`));
    card.append(element("p", `Verified: ${release.verified_at ?? "Unknown"}`));
    if (release.approved_at) card.append(element("p", `Approved: ${release.approved_at} by ${release.approved_by ?? "Unknown"}`));
    if (release.active) card.append(element("p", `Activated: ${release.activated_at ?? "Unknown"} by ${release.activated_by ?? "Unknown"}`));
    const verify = element("button", "Verify integrity");
    verify.type = "button";
    verify.className = "sb-button--secondary";
    verify.addEventListener("click", () => void changeRegisteredRelease(release.archive_sha256, "verify"));
    const activate = element("button", release.active ? "Active" : "Activate");
    activate.type = "button";
    activate.className = "sb-button--primary";
    activate.disabled = release.active || !release.available;
    activate.addEventListener("click", () => void changeRegisteredRelease(release.archive_sha256, "activate"));
    card.append(verify, activate);
    releaseList.append(card);
  }
  if (!releaseList.children.length) releaseList.append(element("p", "No releases registered."));
}

async function refreshRegisteredReleases() {
  try {
    const { releases, storage_status } = await requestRegisteredReleases();
    renderRegisteredReleases(releases);
    const active = releases.find((release) => release.active);
    releaseActiveStatus.textContent = active?.available
      ? `Active installation version: v${active.version}`
      : active
        ? `Active installation version: v${active.version} (artifact unavailable)`
        : "Active installation version: Not available";
    releaseManagementStatus.textContent = storage_status === "Release store and staging directory: available."
      ? `${releases.length} registered release${releases.length === 1 ? "" : "s"}.`
      : storage_status;
    markDashboardFresh(new Date().toISOString());
  } catch (_) {
    releaseActiveStatus.textContent = "Active installation version: Not available";
    releaseManagementStatus.textContent = "Release registry unavailable. Check server configuration and database readiness.";
    markDashboardStale();
  }
}

async function changeRegisteredRelease(digest, action) {
  if (action === "activate" && !window.confirm("Activate this verified artifact for future installations? Existing agents will not be upgraded.")) return;
  releaseManagementStatus.textContent = action === "activate" ? "Activating release…" : "Verifying release…";
  try {
    await requestDashboardMutation(`/api/v1/agent-releases/${digest}/${action}`, "POST", {});
    await refreshRegisteredReleases();
  } catch (_) {
    releaseManagementStatus.textContent = "Release change failed. Check artifact integrity and server logs.";
  }
}

async function registerRelease(event) {
  event.preventDefault();
  const name = releaseRegisterName.value.trim();
  if (!/^skybeat-agent-[0-9]+\.[0-9]+\.[0-9]+$/.test(name)) {
    releaseManagementStatus.textContent = "Enter a staged release name in skybeat-agent-MAJOR.MINOR.PATCH format.";
    return;
  }
  releaseRegisterSubmit.disabled = true;
  releaseManagementStatus.textContent = "Registering and verifying release…";
  try {
    await requestDashboardMutation("/api/v1/agent-releases", "POST", { name });
    releaseRegisterName.value = "";
    await refreshRegisteredReleases();
  } catch (_) {
    await refreshRegisteredReleases();
    if (!/^(Release store:|Release staging:|Release registry unavailable)/.test(releaseManagementStatus.textContent)) {
      releaseManagementStatus.textContent = "Registration failed. Confirm the staged bundle and ZIP are complete and valid.";
    }
  } finally {
    releaseRegisterSubmit.disabled = false;
  }
}

function openDeploymentDeleteDialog(deployment) {
  pendingDeploymentDeletion = deployment;
  deploymentDeleteStatus.textContent = "";
  deploymentDeleteConfirm.disabled = false;
  deploymentDeleteDialog.showModal();
}

function closeDeploymentDeleteDialog() {
  deploymentDeleteDialog.close();
  pendingDeploymentDeletion = null;
}

async function deleteDeployment() {
  if (pendingDeploymentDeletion === null) return;
  deploymentDeleteConfirm.disabled = true;
  deploymentDeleteStatus.textContent = "Deleting prepared device…";
  try {
    await requestDashboardMutation(`/api/v1/agent-enrollments/${encodeURIComponent(pendingDeploymentDeletion.enrollment_id)}`, "DELETE", {});
    closeDeploymentDeleteDialog();
    await refreshDeploymentsView();
    deploymentsStatus.textContent = "Prepared device deleted.";
  } catch (_) {
    deploymentDeleteConfirm.disabled = false;
    deploymentDeleteStatus.textContent = "Prepared device could not be deleted. It remains in To Install.";
  }
}

async function refreshDeploymentsView() {
  if (refreshing) return;
  refreshing = true;
  try {
    const [items, release] = await Promise.allSettled([requestToInstallDeployments(), requestReleaseMetadata()]);
    if (items.status !== "fulfilled") throw new Error("deployment refresh failed");
    toInstallDeployments = items.value.filter((item) => item && typeof item.enrollment_id === "string" && typeof item.device_name === "string" && typeof item.project_name === "string" && typeof item.state === "string");
    deploymentRelease = release.status === "fulfilled" ? release.value : null;
    renderDeployments();
    if (deploymentRelease === null) {
      deploymentsStatus.className = "deployment-release-status deployment-release-status--warning";
      deploymentsStatus.textContent = "Approved agent package unavailable. Review the active artifact in Release Management below.";
    } else {
      deploymentsStatus.className = "deployment-release-status";
      deploymentsStatus.textContent = `${toInstallDeployments.length} device${toInstallDeployments.length === 1 ? "" : "s"} waiting for installation.`;
    }
    markDashboardFresh(null);
  } catch (_) { deploymentsStatus.textContent = "Pending deployments could not be loaded. Existing data may be stale."; markDashboardStale(); }
  finally { refreshing = false; scheduleRefresh(); }
}

function openUserDialog(user = null) {
  editingUserId = user?.user_id ?? null;
  userForm.reset();
  userFormStatus.textContent = "";
  userEmail.disabled = user !== null;
  userEmail.required = user === null;
  document.getElementById("user-dialog-title").textContent = user === null ? "Add dashboard user" : "Edit dashboard user";
  userSubmit.textContent = user === null ? "Create user" : "Save changes";
  if (user !== null) {
    userName.value = user.name || "";
    userEmail.value = user.email;
    userRole.value = user.role;
    userActive.checked = user.active;
  }
  userDialog.showModal();
  userName.focus();
}

function closeUserDialog() {
  userDialog.close();
  editingUserId = null;
}

async function submitUser() {
  const payload = {
    display_name: userName.value.trim() || null,
    role: userRole.value,
    is_active: userActive.checked,
  };
  if (editingUserId === null) payload.email = userEmail.value.trim();
  if (editingUserId === null && !payload.email) {
    userFormStatus.textContent = "Enter a Google email address.";
    return;
  }
  userSubmit.disabled = true;
  try {
    await requestDashboardMutation(
      editingUserId === null ? "/api/v1/users" : `/api/v1/users/${editingUserId}`,
      editingUserId === null ? "POST" : "PATCH",
      payload,
    );
    closeUserDialog();
    await refreshUsersView();
  } catch (_) {
    userFormStatus.textContent = "The user change was not accepted. Review the account and role.";
  } finally {
    userSubmit.disabled = false;
  }
}

async function refreshActiveView() {
  if (dashboardView === "devices") return refreshDashboard();
  if (dashboardView === "device_detail") return refreshDeviceDetailPage();
  if (dashboardView === "projects") return refreshProjectsView();
  if (dashboardView === "users") return refreshUsersView();
  if (dashboardView === "deployments") return refreshDeploymentsView();
  if (dashboardView === "releases") return refreshRegisteredReleases();
  if (dashboardView === "notifications") return refreshNotificationsView();
  return refreshOverviewView();
}

function renderDeviceDetailPage(device) {
  document.getElementById("device-page-name").textContent = displayValue(device.name);
  document.getElementById("device-breadcrumb-name").textContent = displayValue(device.name);
  document.getElementById("device-page-context").textContent = [device.project?.name, device.hostname].filter(Boolean).join(" · ");
  const availability = statusPill(device.state);
  availability.id = "device-page-availability";
  document.getElementById("device-page-availability").replaceWith(availability);
  const gpuPill = statusPill(device.gpu_health?.effective);
  gpuPill.id = "device-page-gpu";
  document.getElementById("device-page-gpu").replaceWith(gpuPill);
  const osLabel = conciseOsLabel(device.os);
  const lastSeen = device.pending_first_heartbeat ? "Awaiting first heartbeat" : formatRelativeTime(device.last_seen_at);
  document.getElementById("device-page-hero-meta").textContent = `${osLabel} · Last seen: ${lastSeen}`;
  document.getElementById("device-page-stale").hidden = device.telemetry_stale !== true;
  logWatchState.offline = device.state === "OFFLINE";
  updateLogWatchOffline();
  detailPairs(document.getElementById("device-page-communication"), [
    ["Availability", device.state],
    ["Last heartbeat", device.last_seen_at ? timestampNode(device.last_seen_at) : "Awaiting first heartbeat"],
  ]);
  detailPairs(document.getElementById("device-page-system"), [
    ["Operating system", osLabel], ["Hostname", device.hostname ?? "Not reported"],
    ["Kernel", device.os?.kernel ?? "Not reported"], ["Architecture", device.os?.architecture ?? "Not reported"],
  ]);
  detailPairs(document.getElementById("device-page-gpu-summary"), [
    ["Current GPU state", device.gpu_health?.effective ?? "Not available"],
    ["Reported GPU state", device.gpu_health?.reported ?? "Not reported"],
  ]);
  detailPairs(document.getElementById("device-page-project"), [["Assigned project", device.project?.name]]);
  const notices = deviceAttention(device);
  const attention = document.getElementById("device-page-attention");
  attention.replaceChildren();
  for (const kind of ["communication", "gpu"]) {
    const notice = notices.find((item) => item.kind === kind);
    const label = kind === "communication" ? "Communication" : "GPU";
    const value = notice?.label.slice(label.length + 2) ?? (kind === "gpu" && !device.latest_received_at ? "Awaiting telemetry" : "No current attention");
    attention.append(detailFact(label, value));
  }
  detailPairs(document.getElementById("device-page-inspection"), [
    ["Communication", device.state], ["GPU", device.gpu_health?.effective],
    ["Operating system", osLabel], ["Last contact", device.last_seen_at ? timestampNode(device.last_seen_at) : "Awaiting first heartbeat"],
    ["Known attention", notices.length ? notices.map((item) => item.label).join("; ") : "No current attention"],
  ]);
}

function lifecycleActionEligible(action) {
  if (!canManage || !lifecycleAvailable || lifecycleSubmitting || !lifecycleState) return false;
  if (action === "upgrade") {
    return lifecycleState.actions?.upgrade === true && lifecycleState.compatibility === "UPGRADE_AVAILABLE"
      && Boolean(lifecycleState.latest_approved_version);
  }
  if (action === "rollback") {
    const operation = lifecycleState.operation;
    return lifecycleState.actions?.rollback === true && operation?.state === "SUCCEEDED"
      && operation.rollback_available === true && Boolean(operation.previous_version);
  }
  return false;
}

function updateLifecycleActions() {
  if (lifecycleUpgrade) {
    lifecycleUpgrade.hidden = !lifecycleActionEligible("upgrade");
    lifecycleUpgrade.disabled = lifecycleUpgrade.hidden;
  }
  if (lifecycleRollback) {
    lifecycleRollback.hidden = !lifecycleActionEligible("rollback");
    lifecycleRollback.disabled = lifecycleRollback.hidden;
  }
}

async function refreshAgentLifecycle() {
  const generation = ++lifecycleGeneration;
  const deviceId = deviceDetailPage.dataset.deviceId;
  lifecycleAvailable = false;
  updateLifecycleActions();
  if (lifecycleState) lifecycleStatus.textContent = "Refreshing agent lifecycle state. Last verified state is retained.";
  try {
    const response = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/agent-lifecycle`, {
      credentials: "same-origin", signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error("lifecycle read failed");
    const payload = await response.json();
    if (generation !== lifecycleGeneration) return;
    if (!payload || typeof payload !== "object") throw new Error("invalid lifecycle state");
    lifecycleState = payload;
    lifecycleAvailable = true;
    const operation = payload.operation;
    const failure = operation?.failure_category
      ? [operation.failure_category, operation.failure_detail].filter(Boolean).map((value) => value.replaceAll("_", " ")).join(" · ")
      : "None";
    detailPairs(lifecycleFacts, [
      ["Reported version", payload.compatibility === "BOOTSTRAP_REQUIRED" || !payload.installed_version
        ? "Unknown (legacy agent)" : payload.installed_version],
      ["Latest approved release", payload.latest_approved_version ?? "Unavailable"],
      ["Compatibility", (payload.compatibility ?? "UNKNOWN").replaceAll("_", " ")],
      ["Operation", operation ? `${operation.action} · ${operation.state.replaceAll("_", " ")}` : "None"],
      ["Last failure", failure],
    ]);
    if (payload.compatibility === "BOOTSTRAP_REQUIRED") {
      lifecycleStatus.textContent = "Managed lifecycle is unsupported by this legacy agent. Install the first capable release with the reviewed installer while preserving identity and configuration.";
    } else if (payload.compatibility === "UNKNOWN") {
      lifecycleStatus.textContent = "Reported agent version is unknown; lifecycle actions are unavailable.";
    } else if (payload.compatibility === "RELEASE_UNAVAILABLE") {
      lifecycleStatus.textContent = "Approved agent release is unavailable. Reported version follows the latest heartbeat.";
    } else if (payload.compatibility === "IN_PROGRESS") {
      lifecycleStatus.textContent = "An agent lifecycle operation is in progress.";
    } else {
      lifecycleStatus.textContent = "Agent lifecycle state loaded. Reported version follows the latest heartbeat.";
    }
    updateLifecycleActions();
  } catch (_) {
    if (generation !== lifecycleGeneration) return;
    lifecycleAvailable = false;
    lifecycleStatus.textContent = "Agent lifecycle state is unavailable. Last successful state is retained.";
    if (!lifecycleState) detailPairs(lifecycleFacts, [["Reported version", "Unavailable"]]);
    updateLifecycleActions();
  }
}

async function submitAgentLifecycle(action) {
  if (!lifecycleActionEligible(action)) return;
  const approved = action === "upgrade" ? lifecycleState.latest_approved_version : lifecycleState.operation?.previous_version;
  const intent = action === "upgrade" ? "upgrade" : "roll back";
  if (!window.confirm(`Request ${intent} for this device to agent ${approved}? The local updater will verify the approved release and check service health.`)) return;
  ++lifecycleGeneration;
  lifecycleSubmitting = true;
  lifecycleAvailable = false;
  updateLifecycleActions();
  try {
    await requestDashboardMutation(`/api/v1/devices/${encodeURIComponent(deviceDetailPage.dataset.deviceId)}/agent-lifecycle/${action}`, "POST", {});
    lifecycleStatus.textContent = `${action === "upgrade" ? "Upgrade" : "Rollback"} requested for this device.`;
    await refreshAgentLifecycle();
  } catch (_) {
    lifecycleAvailable = false;
    lifecycleStatus.textContent = "Lifecycle request was not accepted. Refresh the release state and try again.";
  } finally {
    lifecycleSubmitting = false;
    updateLifecycleActions();
  }
}

function logWindowForRange(range, now = Date.now()) {
  const duration = LOG_RANGE_MS[range] ?? LOG_RANGE_MS["24h"];
  return { from: new Date(now - duration).toISOString(), until: new Date(now).toISOString() };
}

function normalizeLogSearch(value) {
  return value.trim().replace(/\s+/g, " ");
}

function logQueryParams(filters, cursor = null) {
  const query = new URLSearchParams({ limit: String(LOG_PAGE_LIMIT), from: filters.window.from, until: filters.window.until });
  if (filters.source) query.set("source", filters.source);
  if (filters.q) query.set("q", filters.q);
  if (filters.timeBasis === "occurred") query.set("time_basis", "occurred");
  if (cursor) query.set("cursor", cursor);
  return query;
}

async function requestDeviceLogs(deviceId, filters, cursor = null, signal = undefined) {
  const response = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/logs?${logQueryParams(filters, cursor)}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new Error("device logs request failed");
  return response.json();
}

function updateLogWatchOffline() {
  const notice = document.getElementById("log-watch-offline");
  notice.hidden = !logWatchState.offline;
  if (logWatchState.offline) {
    const latest = logWatchState.latestSuccessfulAt;
    notice.textContent = latest
      ? `Device offline. Stored history remains available. Last successful collection: ${new Date(latest).toLocaleString()}.`
      : "Device offline. Stored history remains available; no new collection is expected while it is unreachable.";
  }
}

function syncLogWatchButtons() {
  const older = document.getElementById("log-watch-older");
  older.hidden = !logWatchState.nextCursor;
  older.disabled = logWatchState.loading;
  document.getElementById("log-watch-refresh").disabled = logWatchState.loading;
}

function renderDeviceLogs(payload, append = false) {
  if (!append) {
    logWatchState.items = [];
    logWatchState.sources = payload.sources ?? [];
    logWatchState.latestSuccessfulAt = logWatchState.sources
      .filter((source) => source.status === "available" && source.checked_at)
      .map((source) => source.checked_at)
      .sort()
      .at(-1) ?? null;
  }
  const known = new Set(logWatchState.items.map((item) => item.id));
  for (const item of payload.items ?? []) {
    if (!known.has(item.id)) {
      logWatchState.items.push(item);
      known.add(item.id);
    }
  }
  logWatchState.nextCursor = payload.next_cursor ?? null;
  logWatchState.hasSuccess = true;

  const sourceContainer = document.getElementById("log-watch-sources");
  const states = { available: "Available", permission_unavailable: "Permission unavailable", collection_error: "Collection error", no_report: "No report yet" };
  sourceContainer.replaceChildren();
  for (const source of logWatchState.sources) {
    if (!Object.hasOwn(LOG_SOURCE_LABELS, source.source)) continue;
    const card = document.createElement("section");
    card.className = "device-log-source";
    const state = element("p", states[source.status] ?? "Unavailable");
    const stateClass = Object.hasOwn(states, source.status) ? source.status.replaceAll("_", "-") : "unavailable";
    state.className = `device-log-source__state device-log-source__state--${stateClass}`;
    card.append(element("h4", LOG_SOURCE_LABELS[source.source]), state);
    sourceContainer.append(card);
  }
  if (!logWatchState.sources.length) sourceContainer.append(element("p", "No log reports received yet."));

  const results = document.getElementById("log-watch-results");
  results.replaceChildren();
  for (const entry of logWatchState.items) {
    const row = document.createElement("li");
    const metadata = element("span", `${new Date(entry.occurred_at ?? entry.received_at).toLocaleString()} · ${LOG_SOURCE_LABELS[entry.source] ?? entry.source}${entry.severity ? ` · ${entry.severity}` : ""}`);
    metadata.className = "device-log-entry__meta";
    const message = element("p", entry.message);
    message.className = "device-log-entry__message";
    row.append(metadata, message);
    results.append(row);
  }
  const summary = document.getElementById("log-watch-summary");
  summary.textContent = logWatchState.items.length
    ? `Showing ${logWatchState.items.length} stored log entries.`
    : logWatchState.sources.every((source) => source.status === "no_report")
      ? "No diagnostics collected yet."
      : "No stored logs match these filters.";
  if (logWatchState.latestSuccessfulAt) {
    summary.textContent += ` Last successful collection: ${new Date(logWatchState.latestSuccessfulAt).toLocaleString()}.`;
  }
  document.getElementById("log-watch-status").textContent = append ? "Older logs loaded." : "Stored logs loaded.";
  updateLogWatchOffline();
  syncLogWatchButtons();
}

async function loadDeviceLogs({ older = false, auto = false } = {}) {
  if (older && (logWatchState.loading || !logWatchState.nextCursor)) return;
  if (auto && (logWatchState.loading || logWatchState.olderLoaded)) return;
  if (!older && logWatchState.controller) logWatchState.controller.abort();
  const generation = ++logWatchState.generation;
  const controller = new AbortController();
  logWatchState.controller = controller;
  logWatchState.loading = true;
  if (!older) logWatchState.window = logWatchState.contextWindow ?? logWindowForRange(logWatchState.range);
  const filters = { source: logWatchState.source, q: logWatchState.q, window: logWatchState.window,
    timeBasis: logWatchState.contextWindow ? "occurred" : "received" };
  const cursor = older ? logWatchState.nextCursor : null;
  if (!older) logWatchState.olderLoaded = false;
  lastLogAttemptAt = Date.now();
  document.getElementById("log-watch-status").textContent = older ? "Loading older logs…" : "Loading stored logs…";
  syncLogWatchButtons();
  try {
    const payload = await requestDeviceLogs(deviceDetailPage.dataset.deviceId, filters, cursor, controller.signal);
    if (generation !== logWatchState.generation) return;
    renderDeviceLogs(payload, older);
    if (older) logWatchState.olderLoaded = true;
  } catch (error) {
    if (generation !== logWatchState.generation || error.name === "AbortError") return;
    document.getElementById("log-watch-status").textContent = logWatchState.hasSuccess
      ? "Log refresh failed. Last successful logs are retained."
      : "Logs could not be loaded. Try Refresh logs.";
  } finally {
    if (generation === logWatchState.generation) {
      logWatchState.loading = false;
      logWatchState.controller = null;
      syncLogWatchButtons();
    }
  }
}

function initializeLogWatch() {
  const source = document.getElementById("log-watch-source");
  const range = document.getElementById("log-watch-range");
  const search = document.getElementById("log-watch-search");
  for (const [value, label] of Object.entries(LOG_SOURCE_LABELS)) {
    source.append(new Option(label, value));
  }
  source.addEventListener("change", () => {
    logWatchState.source = source.value;
    void loadDeviceLogs();
  });
  range.addEventListener("change", () => {
    logWatchState.range = range.value;
    if (range.value !== "incident") {
      logWatchState.contextWindow = null;
      range.querySelector('option[value="incident"]')?.remove();
    }
    void loadDeviceLogs();
  });
  document.getElementById("log-watch-search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    logWatchState.q = normalizeLogSearch(search.value);
    search.value = logWatchState.q;
    void loadDeviceLogs();
  });
  document.getElementById("log-watch-reset").addEventListener("click", () => {
    source.value = "";
    range.value = "24h";
    range.querySelector('option[value="incident"]')?.remove();
    search.value = "";
    logWatchState.source = "";
    logWatchState.range = "24h";
    logWatchState.q = "";
    logWatchState.contextWindow = null;
    void loadDeviceLogs();
  });
  document.getElementById("log-watch-refresh").addEventListener("click", () => void loadDeviceLogs());
  document.getElementById("log-watch-older").addEventListener("click", () => void loadDeviceLogs({ older: true }));
}

async function refreshDeviceDetailPage() {
  if (refreshing) return;
  refreshing = true;
  const deviceId = deviceDetailPage.dataset.deviceId;
  void refreshAgentLifecycle();
  const now = Date.now();
  if (now - lastLogAttemptAt >= (document.hidden ? 60000 : 30000)) void loadDeviceLogs({ auto: true });
  try {
    const device = await requestDeviceDetail(deviceId);
    renderDeviceDetailPage(device);
    document.getElementById("device-page-status").textContent = "Current device state loaded.";
    markDashboardFresh(device.server_time ?? new Date().toISOString());
  } catch (_) {
    document.getElementById("device-page-status").textContent = "Device status refresh failed. Last successful state is retained.";
    markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

async function requestIncidentDiagnostics(deviceId, incidentId, point, signal) {
  const path = `/api/v1/devices/${encodeURIComponent(deviceId)}/incidents/${encodeURIComponent(incidentId)}/diagnostics`;
  const response = await fetch(`${path}?point=${encodeURIComponent(point)}`, { credentials: "same-origin", signal });
  if (!response.ok) {
    const error = new Error("incident diagnostics request failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function renderIncidentChoices(items) {
  const container = document.getElementById("incident-diagnostics-list");
  container.replaceChildren();
  if (!items.length) {
    container.append(element("p", "No incidents for this device."));
    return;
  }
  for (const incident of items) {
    const row = document.createElement("article");
    row.className = "incident-diagnostics__incident";
    const details = element("p", `${incident.type === "GPU" ? "GPU" : "Availability"} · ${incident.status} · ${new Date(incident.opened_at).toLocaleString()}`);
    const actions = document.createElement("div");
    actions.className = "incident-diagnostics__actions";
    const opened = element("button", "Nearby diagnostics");
    opened.type = "button";
    opened.className = "sb-button--secondary";
    opened.setAttribute("aria-label", `Nearby diagnostics for ${incident.type} incident opened ${new Date(incident.opened_at).toLocaleString()}`);
    opened.addEventListener("click", () => void loadIncidentDiagnostics(incident.incident_id, "opened"));
    actions.append(opened);
    if (incident.closed_at) {
      const recovered = element("button", "Recovery diagnostics");
      recovered.type = "button";
      recovered.className = "sb-button--secondary";
      recovered.setAttribute("aria-label", `Recovery diagnostics for ${incident.type} incident closed ${new Date(incident.closed_at).toLocaleString()}`);
      recovered.addEventListener("click", () => void loadIncidentDiagnostics(incident.incident_id, "recovered"));
      actions.append(recovered);
    }
    row.append(details, actions);
    container.append(row);
  }
}

async function loadDevicePageIncidents() {
  const generation = ++incidentDiagnosticsState.listGeneration;
  const status = document.getElementById("incident-diagnostics-status");
  status.textContent = "Loading incidents…";
  try {
    const result = await requestDeviceIncidents(deviceDetailPage.dataset.deviceId);
    if (generation !== incidentDiagnosticsState.listGeneration) return;
    renderIncidentChoices(result.items ?? []);
    status.textContent = "Select an incident to inspect nearby stored diagnostics.";
  } catch (_) {
    if (generation === incidentDiagnosticsState.listGeneration) {
      status.textContent = "Incidents are currently unavailable. Try Refresh incidents.";
    }
  }
}

function renderIncidentDiagnostics(payload) {
  incidentDiagnosticsState.payload = payload;
  const incident = payload.incident;
  const point = incident.point === "recovered" ? "Recovery" : "Opening";
  document.getElementById("incident-diagnostics-context").textContent =
    `${incident.type === "GPU" ? "GPU" : "Availability"} · ${point} at ${new Date(incident.anchor_at).toLocaleString()} · Nearby diagnostics by event time.`;
  const results = document.getElementById("incident-diagnostics-results");
  results.replaceChildren();
  for (const entry of payload.diagnostics ?? []) {
    const row = document.createElement("li");
    const metadata = element("span", `${new Date(entry.occurred_at).toLocaleString()} · ${LOG_SOURCE_LABELS[entry.source] ?? entry.source}${entry.severity ? ` · ${entry.severity}` : ""}`);
    metadata.className = "device-log-entry__meta";
    const message = element("p", entry.message);
    message.className = "device-log-entry__message";
    row.append(metadata, message);
    results.append(row);
  }
  document.getElementById("incident-diagnostics-result-status").textContent = results.childElementCount
    ? `${results.childElementCount} nearby diagnostics shown.${payload.truncated ? " Preview limited to 50 entries; open Log Watch for more." : ""}`
    : "No stored diagnostics were captured around this incident.";
  document.getElementById("incident-open-log-watch").hidden = false;
}

async function loadIncidentDiagnostics(incidentId, point) {
  incidentDiagnosticsState.controller?.abort();
  const generation = ++incidentDiagnosticsState.generation;
  const controller = new AbortController();
  incidentDiagnosticsState.controller = controller;
  incidentDiagnosticsState.payload = null;
  document.getElementById("incident-diagnostics-preview").hidden = false;
  document.getElementById("incident-diagnostics-context").textContent = "";
  document.getElementById("incident-diagnostics-results").replaceChildren();
  document.getElementById("incident-open-log-watch").hidden = true;
  const status = document.getElementById("incident-diagnostics-result-status");
  status.textContent = "Loading nearby diagnostics…";
  try {
    const payload = await requestIncidentDiagnostics(deviceDetailPage.dataset.deviceId, incidentId, point, controller.signal);
    if (generation !== incidentDiagnosticsState.generation) return;
    renderIncidentDiagnostics(payload);
  } catch (error) {
    if (generation !== incidentDiagnosticsState.generation || error.name === "AbortError") return;
    status.textContent = error.status === 404
      ? "Incident or device was not found."
      : error.status === 401 || error.status === 403
        ? "You are not authorized to view these diagnostics."
        : error.status === 422
          ? "This incident has no recovery time."
          : "Nearby diagnostics are temporarily unavailable. Try the incident again.";
  } finally {
    if (generation === incidentDiagnosticsState.generation) incidentDiagnosticsState.controller = null;
  }
}

function openIncidentInLogWatch() {
  const payload = incidentDiagnosticsState.payload;
  if (!payload) return;
  const range = document.getElementById("log-watch-range");
  if (!range.querySelector('option[value="incident"]')) range.append(new Option("Incident window", "incident"));
  range.value = "incident";
  document.getElementById("log-watch-source").value = "";
  document.getElementById("log-watch-search").value = "";
  logWatchState.source = "";
  logWatchState.q = "";
  logWatchState.range = "incident";
  logWatchState.contextWindow = { from: payload.window_start, until: payload.window_end };
  document.getElementById("device-tab-log-watch").click();
  void loadDeviceLogs();
}

function initializeIncidentCorrelation() {
  document.getElementById("incident-diagnostics-refresh").addEventListener("click", () => void loadDevicePageIncidents());
  document.getElementById("incident-open-log-watch").addEventListener("click", openIncidentInLogWatch);
  void loadDevicePageIncidents();
  const query = new URLSearchParams(window.location.search);
  const incidentId = query.get("incident");
  if (incidentId && CANONICAL_UUID.test(incidentId)) {
    document.getElementById("device-tab-analyze").click();
    void loadIncidentDiagnostics(incidentId, query.get("point") === "recovered" ? "recovered" : "opened");
  }
}

function initializeDeviceDetailTabs() {
  const tabs = [document.getElementById("device-tab-log-watch"), document.getElementById("device-tab-analyze")];
  function selectTab(index, focus = false) {
    tabs.forEach((tab, position) => {
      const selected = position === index;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectTab(index));
    tab.addEventListener("keydown", (event) => {
      const next = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      selectTab(next, true);
    });
  });
}

function detailPairs(target, pairs) {
  target.replaceChildren();
  for (const [label, value] of pairs) {
    const definition = document.createElement("dd");
    if (value instanceof Node) definition.append(value);
    else definition.textContent = displayValue(value);
    target.append(element("dt", label), definition);
  }
}

function formatDuration(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "â€”";
  const totalSeconds = Math.floor(value);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function detailFact(label, value) {
  const fact = document.createElement("div");
  fact.className = "detail-fact";
  fact.append(element("span", label));
  if (value instanceof Node) fact.append(value);
  else fact.append(element("strong", displayValue(value)));
  return fact;
}

function renderDetailIdentitySummary(device) {
  detailIdentitySummary.replaceChildren();
  const values = [device.hostname, device.name, device.project?.name].filter(
    (value, index, entries) => value && entries.indexOf(value) === index
  );
  detailIdentitySummary.textContent = values.join(" · ");
}

function renderDetailStateSummary(device) {
  detailStateSummary.replaceChildren(
    detailFact("Device UUID", device.device_id),
    detailFact("Availability", statusPill(device.state)),
    detailFact("GPU state", statusPill(device.gpu_health?.effective)),
    detailFact("Last seen", timestampNode(device.last_seen_at))
  );
}

function renderDiagnosticSummary(device) {
  detailDiagnosticSummary.replaceChildren(
    detailFact("Canonical availability", statusPill(device.state)),
    detailFact("Canonical GPU state", statusPill(device.gpu_health?.effective)),
    detailFact("Reported GPU state", statusPill(device.gpu_health?.reported)),
    detailFact("Telemetry freshness", device.telemetry_stale === true ? "STALE" : "Current")
  );
}

function renderResourceTelemetry(target, resources) {
  target.replaceChildren();
  const available = resources.filter((resource) => typeof resource.value === "number" && Number.isFinite(resource.value));
  if (!available.length) {
    target.append(
      element(
        "p",
        `No reported ${resources.map((resource) => resource.label.toLowerCase()).join(" or ")} telemetry available.`
      )
    );
    return;
  }
  for (const resource of available) {
    const value = Math.max(0, Math.min(100, resource.value));
    const card = document.createElement("div");
    card.className = "detail-resource";
    const header = document.createElement("div");
    header.className = "detail-resource-header";
    header.append(element("strong", resource.label), element("span", formatPercent(resource.value)));
    const meter = document.createElement("div");
    meter.className = "detail-resource-meter";
    meter.setAttribute("role", "progressbar");
    meter.setAttribute("aria-label", `${resource.label}: ${formatPercent(resource.value)}`);
    meter.setAttribute("aria-valuemin", "0");
    meter.setAttribute("aria-valuemax", "100");
    meter.setAttribute("aria-valuenow", String(value));
    const fill = document.createElement("span");
    fill.style.width = `${value}%`;
    meter.append(fill);
    card.append(header, meter);
    target.append(card);
  }
}

function formatBytes(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let amount = value;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatTemperature(value) {
  return typeof value === "number" && Number.isFinite(value) ? `${value} °C` : "—";
}

function resetDetailSections() {
  for (const target of [
    detailIdentitySummary,
    detailStateSummary,
    detailDiagnosticSummary,
    detailIdentity,
    detailFreshness,
    detailSystem,
    detailResourceTelemetry,
    detailPolicy,
    detailStorage,
    detailGpus,
    detailIncidents,
  ]) {
    target?.replaceChildren();
  }
  currentDetail = null;
  if (detailOpenPage !== null) detailOpenPage.hidden = true;
  if (detailManagementActions !== null) detailManagementActions.hidden = true;
}

async function requestDeviceDetail(deviceId, signal) {
  const response = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new Error("device detail request failed");
  return response.json();
}

async function requestDeviceIncidents(deviceId, signal) {
  const query = new URLSearchParams({ limit: "20" });
  query.set("device_id", deviceId);
  const response = await fetch(`/api/v1/incidents?${query}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new Error("device incident request failed");
  return response.json();
}

function renderDetail(device) {
  currentDetail = device;
  detailOpenPage.href = `/dashboard/devices/${encodeURIComponent(device.device_id)}`;
  detailOpenPage.hidden = false;
  detailManagementActions.hidden = dashboardView !== "devices" || !canManage;
  detailTitle.textContent = `Device detail: ${displayValue(device.name)}`;
  renderDetailIdentitySummary(device);
  renderDetailStateSummary(device);
  renderDiagnosticSummary(device);
  detailPairs(detailIdentity, [
    ["Device name", device.name],
    ["Device UUID", device.device_id],
    ["Project", device.project?.name],
    ["Monitoring", device.monitoring_enabled === true ? "Enabled" : "Disabled"],
  ]);
  detailPairs(detailFreshness, [
    ["Canonical availability", device.state],
    ["Last seen", timestampNode(device.last_seen_at)],
    ["Latest telemetry receipt", timestampNode(device.latest_received_at)],
    ["Telemetry sample collected", timestampNode(device.collected_at)],
    ["Dashboard refresh", timestampNode(device.server_time)],
    ["Telemetry freshness", device.telemetry_stale === true ? "STALE" : "Current"],
  ]);
  const os = device.os ?? {};
  detailPairs(detailSystem, [
    ["Hostname", device.hostname],
    ["Primary IP", device.primary_ip],
    ["IP addresses", Array.isArray(device.ip_addresses) ? device.ip_addresses.join(", ") : null],
    ["Operating system", conciseOsLabel(os)],
    ["Kernel", os.kernel],
    ["Architecture", os.architecture],
    ["Agent version", device.agent_version],
    ["Uptime", formatDuration(device.uptime_seconds)],
  ]);
  renderResourceTelemetry(detailResourceTelemetry, [
    { label: "CPU utilization", value: device.cpu?.utilization_percent },
    { label: "Memory utilization", value: device.memory?.utilization_percent },
  ]);
  renderStorage(device.disks);
  renderGpus(device.gpus, device.gpu_health);
  const policy = device.expected_gpu_policy ?? {};
  detailPairs(detailPolicy, [
    ["Minimum expected GPU count", policy.minimum_count],
    ["Expected GPU UUIDs", Array.isArray(policy.uuids) ? policy.uuids.join(", ") : null],
  ]);
}

function renderStorage(disks) {
  const items = Array.isArray(disks) ? disks : [];
  if (!items.length) {
    detailStorage.replaceChildren(element("p", "No storage telemetry available."));
    return;
  }
  const list = document.createElement("div");
  list.className = "detail-card-list";
  for (const disk of items) {
    const card = document.createElement("article");
    card.className = "detail-card";
    card.append(element("h4", `Filesystem: ${displayValue(disk.mountpoint ?? disk.path)}`));
    const values = document.createElement("dl");
    detailPairs(values, [
      ["Total", formatBytes(disk.total_bytes)],
      ["Used", formatBytes(disk.used_bytes)],
      ["Available", formatBytes(disk.free_bytes ?? disk.available_bytes)],
      ["Utilization", formatPercent(disk.utilization_percent)],
    ]);
    const utilization = document.createElement("div");
    renderResourceTelemetry(utilization, [{ label: "Disk utilization", value: disk.utilization_percent }]);
    card.append(values, utilization);
    list.append(card);
  }
  detailStorage.replaceChildren(list);
}

function renderGpus(gpus, gpuHealth) {
  const items = Array.isArray(gpus) ? gpus : [];
  if (!items.length) {
    detailGpus.replaceChildren(element("p", "No GPU telemetry available."));
    return;
  }
  const list = document.createElement("div");
  list.className = "detail-card-list";
  for (const gpu of items) {
    const card = document.createElement("article");
    card.className = "detail-card";
    card.append(element("h4", displayValue(gpu.name ?? gpu.model ?? gpu.uuid)));
    const values = document.createElement("dl");
    detailPairs(values, [
      ["Index", gpu.index],
      ["GPU UUID", gpu.uuid],
      ["Reported GPU state", gpuHealth?.reported],
      ["Canonical GPU state", gpuHealth?.effective],
      ["Utilization", formatPercent(gpu.utilization_percent)],
      ["Temperature", formatTemperature(gpu.temperature_celsius)],
      ["Memory used", formatBytes(gpu.memory_used_bytes)],
      ["Memory total", formatBytes(gpu.memory_total_bytes)],
    ]);
    const utilization = document.createElement("div");
    renderResourceTelemetry(utilization, [{ label: "GPU utilization", value: gpu.utilization_percent }]);
    card.append(values, utilization);
    list.append(card);
  }
  detailGpus.replaceChildren(list);
}

function renderIncidents(items) {
  const incidents = Array.isArray(items) ? items : [];
  if (!incidents.length) {
    detailIncidents.replaceChildren(element("p", "No recent incidents for this device."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "detail-incident-list";
  for (const incident of incidents) {
    const item = document.createElement("li");
    item.append(
      element("strong", `${displayValue(incident.type)} — ${displayValue(incident.status)}`),
      element("span", `Reason: ${displayValue(incident.reason)}`),
      element("span", `Opened: ${displayValue(incident.opened_at)}`),
      element("span", `Closed: ${displayValue(incident.closed_at)}`),
      element("span", `Resolution: ${displayValue(incident.resolution)}`)
    );
    const point = incident.status === "CLOSED" ? "recovered" : "opened";
    const preview = element("a", "Nearby diagnostics");
    preview.href = `/dashboard/devices/${encodeURIComponent(incident.device_id)}?incident=${encodeURIComponent(incident.incident_id)}&point=${point}`;
    item.append(preview);
    list.append(item);
  }
  detailIncidents.replaceChildren(list);
}

function renderIncidentFailure() {
  detailIncidents.replaceChildren(element("p", "Recent incidents are currently unavailable."));
}

function createSvgElement(name) {
  return document.createElementNS("http://www.w3.org/2000/svg", name);
}

function numericHistoryValue(value) {
  if (value === 0) return 0;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function historyPoints(points) {
  if (!Array.isArray(points)) return [];
  return points.map((point) => {
    const timestamp = typeof point?.received_at === "string" ? Date.parse(point.received_at) : NaN;
    return {
      timestamp,
      value: numericHistoryValue(point?.value),
    };
  });
}

function historySeriesName(series) {
  if (series.identity?.kind === "uuid") return `GPU UUID: ${displayValue(series.identity.value)}`;
  if (series.identity?.kind === "index") return `GPU index: ${displayValue(series.identity.value)}`;
  return "GPU identity unavailable";
}

function historyColor(index) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(HISTORY_COLOR_TOKENS[index % HISTORY_COLOR_TOKENS.length])
    .trim();
}

function usableHistoryPoints(points) {
  return points.filter((point) => Number.isFinite(point.timestamp) && point.value !== null);
}

function historyBounds(series, percentage) {
  const values = series.flatMap((item) => usableHistoryPoints(item.points).map((point) => point.value));
  const timestamps = series.flatMap((item) => usableHistoryPoints(item.points).map((point) => point.timestamp));
  if (!values.length || !timestamps.length) return null;
  const minValue = percentage ? Math.min(0, ...values) : Math.min(...values);
  const maxValue = percentage ? Math.max(100, ...values) : Math.max(...values);
  const valuePadding = minValue === maxValue ? Math.max(1, Math.abs(minValue) * 0.1) : 0;
  const minTime = Math.min(...timestamps);
  const maxTime = Math.max(...timestamps);
  const timePadding = maxTime === minTime ? 1 : 0;
  return {
    minValue: minValue - valuePadding,
    maxValue: maxValue + valuePadding,
    minTime: minTime - timePadding,
    maxTime: maxTime + timePadding,
  };
}

function historyLinePath(points, bounds, width, height, padding) {
  const xScale = (timestamp) =>
    padding + ((timestamp - bounds.minTime) / (bounds.maxTime - bounds.minTime)) * (width - padding * 2);
  const yScale = (value) =>
    height - padding - ((value - bounds.minValue) / (bounds.maxValue - bounds.minValue)) * (height - padding * 2);
  let started = false;
  let path = "";
  for (const point of points) {
    if (!Number.isFinite(point.timestamp) || point.value === null) {
      started = false;
      continue;
    }
    const command = started ? "L" : "M";
    path += `${command}${xScale(point.timestamp).toFixed(2)},${yScale(point.value).toFixed(2)} `;
    started = true;
  }
  return path.trim();
}

function formatHistoryMetric(value, units) {
  return value === null ? "—" : `${value}${units}`;
}

function appendHistorySummary(card, series, units) {
  const summary = document.createElement("dl");
  summary.className = "history-summary";
  for (const item of series) {
    const usable = usableHistoryPoints(item.points);
    const values = usable.map((point) => point.value);
    const latest = values.length ? values[values.length - 1] : null;
    summary.append(
      element("dt", item.label),
      element("dd", `Observations: ${usable.length}; latest: ${formatHistoryMetric(latest, units)}; min: ${formatHistoryMetric(values.length ? Math.min(...values) : null, units)}; max: ${formatHistoryMetric(values.length ? Math.max(...values) : null, units)}`)
    );
  }
  card.append(summary);
}

function renderHistoryChart(title, units, series, percentage) {
  const card = document.createElement("article");
  card.className = "history-chart";
  card.append(element("h4", title));
  const bounds = historyBounds(series, percentage);
  if (bounds === null) {
    card.append(element("p", "No usable observations are available for this series."));
    appendHistorySummary(card, series, units);
    return card;
  }
  const width = 600;
  const height = 220;
  const padding = 42;
  const svg = createSvgElement("svg");
  svg.classList.add("history-svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${title} history chart`);
  const axis = createSvgElement("path");
  axis.setAttribute("d", `M${padding},${padding} V${height - padding} H${width - padding}`);
  axis.setAttribute("class", "history-axis");
  svg.append(axis);
  const valueLabel = createSvgElement("text");
  valueLabel.setAttribute("x", String(padding));
  valueLabel.setAttribute("y", "16");
  valueLabel.setAttribute("class", "history-axis-label");
  valueLabel.textContent = `${bounds.maxValue.toFixed(percentage ? 0 : 1)}${units}`;
  const timeLabel = createSvgElement("text");
  timeLabel.setAttribute("x", String(width - padding));
  timeLabel.setAttribute("y", String(height - 10));
  timeLabel.setAttribute("text-anchor", "end");
  timeLabel.setAttribute("class", "history-axis-label");
  timeLabel.textContent = new Date(bounds.maxTime).toISOString().slice(11, 16);
  svg.append(valueLabel, timeLabel);
  for (const [index, item] of series.entries()) {
    const usable = usableHistoryPoints(item.points);
    const path = historyLinePath(item.points, bounds, width, height, padding);
    const color = historyColor(index);
    if (path && usable.length !== 1) {
      const line = createSvgElement("path");
      line.setAttribute("d", path);
      line.setAttribute("class", "history-line");
      line.setAttribute("stroke", color);
      svg.append(line);
    }
    if (usable.length === 1) {
      const point = usable[0];
      const marker = createSvgElement("circle");
      const x =
        padding + ((point.timestamp - bounds.minTime) / (bounds.maxTime - bounds.minTime)) * (width - padding * 2);
      const y =
        height - padding - ((point.value - bounds.minValue) / (bounds.maxValue - bounds.minValue)) * (height - padding * 2);
      marker.setAttribute("cx", x.toFixed(2));
      marker.setAttribute("cy", y.toFixed(2));
      marker.setAttribute("r", "4");
      marker.setAttribute("class", "history-point");
      marker.setAttribute("fill", color);
      svg.append(marker);
    }
  }
  card.append(svg);
  if (series.length > 1) {
    const legend = document.createElement("ul");
    legend.className = "history-legend";
    for (const [index, item] of series.entries()) {
      const legendItem = document.createElement("li");
      const marker = document.createElement("span");
      marker.className = "history-legend-marker";
      marker.style.backgroundColor = historyColor(index);
      legendItem.append(marker, element("span", item.label));
      legend.append(legendItem);
    }
    card.append(legend);
  }
  appendHistorySummary(card, series, units);
  return card;
}

function updateHistoryRangeControls() {
  for (const button of historyRangeControls.querySelectorAll("button[data-history-range]")) {
    button.setAttribute("aria-pressed", String(button.dataset.historyRange === selectedHistoryRange));
  }
}

function clearHistory({ abort = true } = {}) {
  historyGeneration += 1;
  if (abort) historyAbortController?.abort();
  historyAbortController = null;
  historyLastSuccess = null;
  historyContent.replaceChildren();
  historyStatus.textContent = "";
  historyRetry.hidden = true;
  historyTruncation.hidden = true;
  historyTruncation.textContent = "";
}

async function requestDeviceHistory(deviceId, rangeName, signal) {
  const query = new URLSearchParams();
  query.set("range", rangeName);
  const response = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/history?${query}`, {
    credentials: "same-origin",
    signal,
  });
  if (!response.ok) throw new Error("history request failed");
  return response.json();
}

function isCurrentHistoryRequest(generation, deviceId, rangeName) {
  return (
    generation === historyGeneration &&
    deviceId === selectedDeviceId &&
    rangeName === selectedHistoryRange &&
    !detailPanel.hidden
  );
}

function renderHistory(payload) {
  const gpuSeries = Array.isArray(payload.gpu_series) ? payload.gpu_series : [];
  const cpuSeries = [{ label: "CPU", points: historyPoints(payload.cpu_utilization) }];
  const memorySeries = [{ label: "Memory", points: historyPoints(payload.memory_utilization) }];
  const utilizationSeries = gpuSeries.map((series) => ({
    label: historySeriesName(series),
    points: historyPoints(series.utilization),
  }));
  const temperatureSeries = gpuSeries.map((series) => ({
    label: historySeriesName(series),
    points: historyPoints(series.temperature),
  }));
  const allSeries = [cpuSeries, memorySeries, utilizationSeries, temperatureSeries].flat();
  if (!allSeries.some((series) => usableHistoryPoints(series.points).length)) {
    historyContent.replaceChildren(element("p", "No telemetry history is available for this range."));
  } else {
    historyContent.replaceChildren(
      renderHistoryChart("CPU usage", "%", cpuSeries, true),
      renderHistoryChart("Memory usage", "%", memorySeries, true),
      renderHistoryChart("GPU utilization", "%", utilizationSeries, true),
      renderHistoryChart("GPU temperature", " °C", temperatureSeries, false)
    );
  }
  const notices = [];
  if (payload.truncated === true) {
    notices.push("History was bounded by the server; the chart shows the available recent sample window.");
  }
  if (payload.series_truncated === true) notices.push("GPU history series were bounded by the server.");
  historyTruncation.textContent = notices.join(" ");
  historyTruncation.hidden = notices.length === 0;
}

async function loadHistory(deviceId, rangeName = selectedHistoryRange) {
  if (!HISTORY_RANGES.includes(rangeName) || deviceId !== selectedDeviceId || detailPanel.hidden) return;
  historyGeneration += 1;
  const generation = historyGeneration;
  historyAbortController?.abort();
  historyAbortController = new AbortController();
  const { signal } = historyAbortController;
  historyStatus.textContent = "Loading history…";
  historyRetry.hidden = true;
  try {
    const payload = await requestDeviceHistory(deviceId, rangeName, signal);
    if (!isCurrentHistoryRequest(generation, deviceId, rangeName) || signal.aborted) return;
    renderHistory(payload);
    historyLastSuccess = { deviceId, rangeName, payload };
    historyStatus.textContent = `History loaded for ${rangeName}.`;
  } catch (_) {
    if (!isCurrentHistoryRequest(generation, deviceId, rangeName) || signal.aborted) return;
    if (historyLastSuccess?.deviceId === deviceId && historyLastSuccess.rangeName === rangeName) {
      historyStatus.textContent = "History may be stale — refresh failed.";
    } else {
      historyContent.replaceChildren(element("p", "History could not be loaded."));
      historyTruncation.hidden = true;
      historyTruncation.textContent = "";
      historyStatus.textContent = "History could not be loaded.";
    }
    historyRetry.hidden = false;
  }
}

async function refreshOpenHistory() {
  if (selectedDeviceId === null || detailPanel.hidden) return;
  await loadHistory(selectedDeviceId, selectedHistoryRange);
}

function isCurrentDetailRequest(generation, deviceId) {
  return generation === detailGeneration && deviceId === selectedDeviceId;
}

async function loadDetail(deviceId, { focus = false } = {}) {
  detailGeneration += 1;
  const generation = detailGeneration;
  detailAbortController?.abort();
  detailAbortController = new AbortController();
  const { signal } = detailAbortController;
  detailStatus.textContent = "Loading canonical device detail…";
  detailRetry.hidden = true;
  const [deviceResult, incidentResult] = await Promise.allSettled([
    requestDeviceDetail(deviceId, signal),
    requestDeviceIncidents(deviceId, signal),
  ]);
  if (!isCurrentDetailRequest(generation, deviceId) || signal.aborted) return;
  if (deviceResult.status === "fulfilled") {
    renderDetail(deviceResult.value);
    detailLastSuccess = { deviceId, detail: deviceResult.value };
    if (incidentResult.status === "fulfilled") {
      renderIncidents(incidentResult.value.items);
      detailStatus.textContent = "Current device detail.";
    } else {
      renderIncidentFailure();
      detailStatus.textContent = "Device detail loaded; recent incidents are unavailable.";
    }
    void refreshOpenHistory();
    if (focus) detailTitle.focus();
    return;
  }
  if (detailLastSuccess?.deviceId === deviceId) {
    detailStatus.textContent = "Device detail may be stale — refresh failed.";
    if (incidentResult.status === "fulfilled") renderIncidents(incidentResult.value.items);
    else renderIncidentFailure();
    return;
  }
  resetDetailSections();
  detailStatus.textContent = "Unable to load device detail.";
  detailRetry.hidden = false;
  if (focus) detailTitle.focus();
}

function openDetail(deviceId, origin) {
  selectedDeviceId = deviceId;
  detailOrigin = origin;
  detailLastSuccess = null;
  detailPanel.hidden = false;
  detailTitle.textContent = "Loading device detail…";
  detailTitle.focus();
  resetDetailSections();
  clearHistory();
  updateHistoryRangeControls();
  void loadDetail(deviceId, { focus: true });
}

async function refreshOpenDetail() {
  if (selectedDeviceId === null || detailPanel.hidden) return;
  await loadDetail(selectedDeviceId);
}

function closeDetail() {
  detailGeneration += 1;
  detailAbortController?.abort();
  detailAbortController = null;
  clearHistory();
  selectedDeviceId = null;
  detailLastSuccess = null;
  detailPanel.hidden = true;
  detailStatus.textContent = "";
  detailRetry.hidden = true;
  const origin = detailOrigin;
  detailOrigin = null;
  if (origin?.isConnected) origin.focus();
}

function showDialog(dialog) {
  if (!dialog.open) dialog.showModal();
}

function enrollmentDraft() {
  return {
    name: enrollName.value,
    projectId: enrollProject.value,
    description: enrollDescription.value,
  };
}

function clearEnrollmentCredential() {
  enrollmentCredential = null;
  enrollmentId = null;
  enrollmentPreparedWithoutToken = false;
}

function openEnrollmentDialog(draft = null) {
  deviceEnrollForm.reset();
  if (draft !== null) {
    enrollName.value = draft.name;
    enrollProject.value = draft.projectId;
    enrollDescription.value = draft.description;
  }
  clearEnrollmentCredential();
  enrollmentStatus.textContent = "";
  enrollSubmit.disabled = false;
  enrollSubmit.textContent = "Prepare Device";
  deviceEnrollClose.disabled = false;
  enrollCancel.disabled = false;
  newProjectFromEnroll.disabled = false;
  enrollName.disabled = false;
  enrollProject.disabled = false;
  enrollDescription.disabled = false;
  showDialog(deviceEnrollDialog);
  enrollName.focus();
}

function openProjectDialog({ fromEnrollment = false } = {}) {
  projectOpenedFromEnrollment = fromEnrollment;
  projectForm.reset();
  projectStatus.textContent = "";
  projectSubmit.disabled = false;
  showDialog(projectDialog);
  projectName.focus();
}

function closeProjectDialog() {
  const reopenEnrollment = projectOpenedFromEnrollment;
  const draft = pendingEnrollmentDraft;
  projectOpenedFromEnrollment = false;
  pendingEnrollmentDraft = null;
  if (projectDialog.open) projectDialog.close();
  if (reopenEnrollment && draft !== null) openEnrollmentDialog(draft);
}

async function submitProject() {
  if (projectSubmissionInFlight) return;
  const name = projectName.value.trim();
  if (!name) {
    projectStatus.textContent = "Enter a project name.";
    return;
  }
  projectSubmissionInFlight = true;
  projectSubmit.disabled = true;
  projectStatus.textContent = "Creating project…";
  try {
    const payload = await requestDashboardMutation("/api/v1/projects", "POST", { name });
    const projectId = payload?.project?.project_id;
    if (typeof projectId !== "string") throw new Error("project response was invalid");
    const reopenEnrollment = projectOpenedFromEnrollment;
    const draft = pendingEnrollmentDraft;
    projectOpenedFromEnrollment = false;
    pendingEnrollmentDraft = null;
    await refreshCanonicalDashboard();
    projectStatus.textContent = "Project created.";
    projectDialog.close();
    if (reopenEnrollment && draft !== null) {
      draft.projectId = projectId;
      openEnrollmentDialog(draft);
    }
  } catch (error) {
    projectStatus.textContent = projectCreationErrorMessage(error);
  } finally {
    projectSubmissionInFlight = false;
    projectSubmit.disabled = false;
  }
}

async function submitEnrollment() {
  if (enrollmentSubmissionInFlight || enrollmentPreparedWithoutToken) return;
  const name = enrollName.value.trim();
  const projectId = enrollProject.value;
  const description = enrollDescription.value.trim();
  if (enrollmentCredential === null && (!name || !projectId || description.length > 512)) {
    enrollmentStatus.textContent = "Enter a device name, choose a project, and keep the description within 512 characters.";
    return;
  }
  enrollmentSubmissionInFlight = true;
  enrollSubmit.disabled = true;
  deviceEnrollClose.disabled = true;
  enrollCancel.disabled = true;
  newProjectFromEnroll.disabled = true;
  enrollSubmit.textContent = enrollmentCredential === null ? "Preparing..." : "Saving token...";
  enrollmentStatus.textContent = enrollmentCredential === null ? "Preparing device..." : "Saving enrollment token file...";
  try {
    if (enrollmentCredential === null) {
      let payload;
      try {
        payload = await requestDashboardMutation("/api/v1/agent-enrollments", "POST", {
          mode: "NEW", name, project_id: projectId, description: description || null,
        });
      } catch (error) {
        const status = error instanceof Error ? error.status : null;
        enrollmentStatus.textContent = status === 409
          ? "Device preparation conflicts with the current state. Review the project and try again."
          : status === 422
            ? "Device name, project, or description is invalid. Review the fields and try again."
            : "Device could not be prepared. Check the form and try again.";
        return;
      }
      if (
        typeof payload?.token !== "string" || !payload.token.startsWith("sbe1.") ||
        typeof payload?.enrollment?.enrollment_id !== "string"
      ) {
        enrollmentPreparedWithoutToken = true;
        enrollmentStatus.textContent = "Device was prepared, but the token response was invalid. Delete this pending deployment before preparing it again.";
        deviceEnrollClose.disabled = false;
        enrollCancel.disabled = false;
        return;
      }
      enrollmentCredential = payload.token;
      enrollmentId = payload.enrollment.enrollment_id;
      enrollName.disabled = true;
      enrollProject.disabled = true;
      enrollDescription.disabled = true;
    }
    try {
      downloadEnrollmentToken();
      window.location.assign("/dashboard/deployments");
    } catch (_) {
      enrollmentStatus.textContent = "Device prepared, but the enrollment token file could not be saved. Retry saving it; this will not prepare another device.";
      enrollSubmit.textContent = "Save token file and continue";
      enrollSubmit.disabled = false;
    }
  } finally {
    enrollmentSubmissionInFlight = false;
    if (enrollmentCredential === null && !enrollmentPreparedWithoutToken) {
      enrollSubmit.disabled = false;
      enrollSubmit.textContent = "Prepare Device";
      deviceEnrollClose.disabled = false;
      enrollCancel.disabled = false;
      newProjectFromEnroll.disabled = false;
    }
  }
}

async function requestReleaseMetadata() {
  const response = await fetch("/api/v1/agent-releases/current", { credentials: "same-origin" });
  if (!response.ok) throw new Error("agent release request failed");
  const release = (await response.json())?.release;
  if (
    typeof release?.version !== "string" || !/^[0-9]+\.[0-9]+\.[0-9]+$/.test(release.version) ||
    typeof release?.archive_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(release.archive_sha256) ||
    typeof release?.wheel_filename !== "string" ||
    !/^skybeat_agent-[0-9]+\.[0-9]+\.[0-9]+-[A-Za-z0-9_.-]+\.whl$/.test(release.wheel_filename) ||
    typeof release?.wheel_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(release.wheel_sha256) ||
    typeof release?.archive_filename !== "string" ||
    release.archive_filename !== `skybeat-agent-${release.version}-linux.zip` ||
    typeof release?.archive_root !== "string" ||
    release.archive_root !== `skybeat-agent-${release.version}` ||
    typeof release?.server_url !== "string"
  ) throw new Error("agent release response was invalid");
  return release;
}

function installationInstructions(release) {
  const insecureFlag = release.allow_insecure_local_server === true ? " --allow-insecure-local-server" : "";
  const server = `'${release.server_url.replaceAll("'", "'\\''")}'`;
  return `# Download the approved archive using Agent Package on this card.\necho '${release.archive_sha256}  ${release.archive_filename}' | sha256sum -c -\nunzip ${release.archive_filename}\ncd ${release.archive_root}\nchmod +x ./install-agent.sh\nsudo ./install-agent.sh --server ${server} --package ./${release.wheel_filename} --sha256 ${release.wheel_sha256} --wheelhouse ./wheelhouse --lockfile ./requirements.lock --token-file ./enrollment.token${insecureFlag}`;
}

function downloadEnrollmentToken() {
  if (enrollmentCredential === null || enrollmentId === null) throw new Error("token unavailable");
  const tokenFile = new Blob([enrollmentCredential], { type: "text/plain" });
  const url = URL.createObjectURL(tokenFile);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = `skybeat-enrollment-${enrollmentId}.token`;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function openMoveDialog() {
  if (selectedDeviceId === null || currentDetail === null) return;
  populateProjectSelect(moveDeviceProject, "Select a project", currentDetail.project?.project_id);
  moveDeviceDescription.textContent = `Choose a project for ${displayValue(currentDetail.name)}.`;
  moveDeviceStatus.textContent = "";
  moveDeviceSubmit.disabled = false;
  showDialog(moveDeviceDialog);
  moveDeviceProject.focus();
}

async function submitMoveDevice() {
  if (moveSubmissionInFlight || selectedDeviceId === null || currentDetail === null) return;
  const projectId = moveDeviceProject.value;
  if (!projectId) {
    moveDeviceStatus.textContent = "Choose a project.";
    return;
  }
  if (projectId === currentDetail.project?.project_id) {
    moveDeviceStatus.textContent = "Choose a different project to make a change.";
    return;
  }
  moveSubmissionInFlight = true;
  moveDeviceSubmit.disabled = true;
  moveDeviceStatus.textContent = "Changing project…";
  try {
    await requestDashboardMutation(
      `/api/v1/devices/${encodeURIComponent(selectedDeviceId)}/project`,
      "PATCH",
      { project_id: projectId }
    );
    await refreshCanonicalDashboard();
    moveDeviceDialog.close();
  } catch (_) {
    moveDeviceStatus.textContent = "Project could not be changed. Review the selected project and try again.";
  } finally {
    moveSubmissionInFlight = false;
    moveDeviceSubmit.disabled = false;
  }
}

function openMonitoringConfirmation() {
  if (selectedDeviceId === null || currentDetail === null) return;
  pendingMonitoringEnabled = currentDetail.monitoring_enabled !== true;
  monitoringDescription.textContent = pendingMonitoringEnabled
    ? `Enable monitoring for ${displayValue(currentDetail.name)}?`
    : `Disable monitoring for ${displayValue(currentDetail.name)}?`;
  monitoringStatus.textContent = "";
  monitoringSubmit.textContent = pendingMonitoringEnabled ? "Enable monitoring" : "Disable monitoring";
  monitoringSubmit.disabled = false;
  showDialog(monitoringDialog);
  monitoringSubmit.focus();
}

async function submitMonitoringChange() {
  if (
    monitoringSubmissionInFlight ||
    selectedDeviceId === null ||
    currentDetail === null ||
    typeof pendingMonitoringEnabled !== "boolean"
  ) {
    return;
  }
  monitoringSubmissionInFlight = true;
  monitoringSubmit.disabled = true;
  monitoringStatus.textContent = "Changing monitoring…";
  try {
    await requestDashboardMutation(
      `/api/v1/devices/${encodeURIComponent(selectedDeviceId)}/monitoring`,
      "PATCH",
      { enabled: pendingMonitoringEnabled }
    );
    await refreshCanonicalDashboard();
    monitoringDialog.close();
  } catch (_) {
    monitoringStatus.textContent = "Monitoring could not be changed. Try again after reviewing the device.";
  } finally {
    monitoringSubmissionInFlight = false;
    monitoringSubmit.disabled = false;
  }
}

function closeEnrollmentDialog() {
  if (enrollmentSubmissionInFlight || enrollmentCredential !== null) return;
  if (deviceEnrollDialog.open) deviceEnrollDialog.close();
}

function closeMoveDialog() {
  if (moveDeviceDialog.open) moveDeviceDialog.close();
}

function closeMonitoringDialog() {
  if (monitoringDialog.open) monitoringDialog.close();
}

function initializeSharedDetailDrawer() {
  if (detailPanel === null) return;
  detailClose.addEventListener("click", closeDetail);
  detailRetry.addEventListener("click", () => {
    if (selectedDeviceId !== null) void loadDetail(selectedDeviceId, { focus: true });
  });
  for (const button of historyRangeControls.querySelectorAll("button[data-history-range]")) {
    button.addEventListener("click", () => {
      const rangeName = button.dataset.historyRange;
      if (selectedDeviceId === null || !HISTORY_RANGES.includes(rangeName)) return;
      selectedHistoryRange = rangeName;
      updateHistoryRangeControls();
      historyContent.replaceChildren();
      historyTruncation.hidden = true;
      historyTruncation.textContent = "";
      historyLastSuccess = null;
      void loadHistory(selectedDeviceId, rangeName);
    });
  }
  historyRetry.addEventListener("click", () => {
    if (selectedDeviceId !== null) void loadHistory(selectedDeviceId, selectedHistoryRange);
  });
  document.addEventListener("keydown", (event) => {
    const dialogOpen = [projectDialog, deviceEnrollDialog, moveDeviceDialog, monitoringDialog].some(
      (dialog) => dialog?.open
    );
    if (event.key === "Escape" && !dialogOpen && !detailPanel.hidden) closeDetail();
  });
}

initializeSharedDetailDrawer();

if (dashboardView === "devices") {
const projectIdFromUrl = new URLSearchParams(window.location.search).get("project_id");
if (projectIdFromUrl !== null && CANONICAL_UUID.test(projectIdFromUrl)) {
  requestedProjectId = projectIdFromUrl;
}
const sidebarPreference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
if (sidebarPreference === "collapsed") setSidebarCollapsed(true);
else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
sidebarToggle.addEventListener("click", () => {
  toggleSidebar();
});
filters.addEventListener("submit", (event) => {
  event.preventDefault();
  reloadDevices();
});
for (const control of [projectFilter, stateFilter, gpuStateFilter, includeDisabled]) {
  control.addEventListener("change", () => reloadDevices());
}
pageSize.addEventListener("change", () => {
  const selectedLimit = Number(pageSize.value);
  if (![25, 50, 100].includes(selectedLimit)) return;
  pageLimit = selectedLimit;
  resetDevicePagination();
  void reloadDevices();
});
search.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(reloadDevices, SEARCH_DEBOUNCE_MS);
});
resetFilters.addEventListener("click", () => {
  clearDeviceFilters();
});
clearDeviceFiltersButton.addEventListener("click", clearDeviceFilters);
loadMore.addEventListener("click", nextDevicePage);
previousPage.addEventListener("click", () => void previousDevicePage());
devices.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target.closest("button") : null;
  if (target === null) return;
  if (target.dataset.filterName) {
    openFilterPopover(target.dataset.filterName, target);
    return;
  }
  if (target.dataset.filterOption && target.dataset.filterValue !== undefined) {
    const name = target.dataset.filterOption;
    const value = target.dataset.filterValue;
    closeFilterPopover();
    applyDeviceFilter(name, value);
  }
});
addDevice?.addEventListener("click", () => openEnrollmentDialog());
newProjectFromEnroll?.addEventListener("click", () => {
  pendingEnrollmentDraft = enrollmentDraft();
  deviceEnrollDialog.close();
  openProjectDialog({ fromEnrollment: true });
});
projectForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitProject();
});
projectClose.addEventListener("click", closeProjectDialog);
projectCancel.addEventListener("click", closeProjectDialog);
projectDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeProjectDialog();
});
deviceEnrollForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitEnrollment();
});
deviceEnrollClose.addEventListener("click", closeEnrollmentDialog);
enrollCancel.addEventListener("click", closeEnrollmentDialog);
deviceEnrollDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeEnrollmentDialog();
});
deviceEnrollDialog.addEventListener("close", () => {
  clearEnrollmentCredential();
  deviceEnrollForm.reset();
});
if (canManage) detailChangeProject.addEventListener("click", openMoveDialog);
if (canManage) detailToggleMonitoring.addEventListener("click", openMonitoringConfirmation);
moveDeviceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitMoveDevice();
});
monitoringForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitMonitoringChange();
});
for (const identifier of ["move-device-close", "move-device-cancel"]) {
  document.getElementById(identifier).addEventListener("click", closeMoveDialog);
}
for (const identifier of ["monitoring-close", "monitoring-cancel"]) {
  document.getElementById(identifier).addEventListener("click", closeMonitoringDialog);
}
logout.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
  window.location.assign("/login");
});
document.addEventListener("visibilitychange", () => {
  window.clearTimeout(refreshTimer);
  if (document.hidden) {
    if (!refreshing) scheduleRefresh();
    return;
  }
  refreshActiveView();
});
refreshActiveView();
} else if (dashboardView === "device_detail") {
  sidebarToggle.addEventListener("click", () => toggleSidebar());
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  initializeDeviceDetailTabs();
  initializeLogWatch();
  initializeIncidentCorrelation();
  lifecycleUpgrade?.addEventListener("click", () => void submitAgentLifecycle("upgrade"));
  lifecycleRollback?.addEventListener("click", () => void submitAgentLifecycle("rollback"));
  document.addEventListener("visibilitychange", () => {
    window.clearTimeout(refreshTimer);
    if (!document.hidden) void refreshActiveView();
    else scheduleRefresh();
  });
  refreshActiveView();
} else if (dashboardView === "users") {
  sidebarToggle.addEventListener("click", () => toggleSidebar());
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  newUser.addEventListener("click", () => openUserDialog());
  userForm.addEventListener("submit", (event) => { event.preventDefault(); void submitUser(); });
  userClose.addEventListener("click", closeUserDialog);
  userCancel.addEventListener("click", closeUserDialog);
  userDialog.addEventListener("cancel", (event) => { event.preventDefault(); closeUserDialog(); });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  refreshActiveView();
} else if (dashboardView === "notifications") {
  sidebarToggle.addEventListener("click", () => toggleSidebar());
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  refreshActiveView();
} else if (dashboardView === "deployments") {
  sidebarToggle.addEventListener("click", () => toggleSidebar());
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  deploymentDeleteConfirm.addEventListener("click", () => void deleteDeployment());
  deploymentDeleteCancel.addEventListener("click", closeDeploymentDeleteDialog);
  deploymentDeleteDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDeploymentDeleteDialog();
  });
  document.addEventListener("visibilitychange", () => {
    window.clearTimeout(refreshTimer);
    if (!document.hidden) void refreshActiveView();
    else scheduleRefresh();
  });
  refreshActiveView();
} else if (dashboardView === "releases") {
  sidebarToggle.addEventListener("click", () => toggleSidebar());
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  releaseRegisterForm.addEventListener("submit", (event) => void registerRelease(event));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void refreshActiveView();
  });
  refreshActiveView();
} else {
  sidebarToggle.addEventListener("click", () => {
    toggleSidebar();
  });
  logout.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/login");
  });
  newProject?.addEventListener("click", () => openProjectDialog());
  projectForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitProject();
  });
  projectClose.addEventListener("click", closeProjectDialog);
  projectCancel.addEventListener("click", closeProjectDialog);
  projectDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeProjectDialog();
  });
  document.addEventListener("visibilitychange", () => {
    window.clearTimeout(refreshTimer);
    if (!document.hidden) void refreshActiveView();
    else scheduleRefresh();
  });
  const preference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
  if (preference === "collapsed") setSidebarCollapsed(true);
  else setSidebarTogglePresentation(window.matchMedia("(max-width: 900px)").matches);
  refreshActiveView();
}
