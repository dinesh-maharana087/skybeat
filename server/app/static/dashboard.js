"use strict";

const DEFAULT_PAGE_LIMIT = 50;
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const VISIBLE_REFRESH_MS = 15000;
const HIDDEN_REFRESH_MS = 60000;
const SEARCH_DEBOUNCE_MS = 250;
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
let lastLogAttemptAt = 0;
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
    device.href = `/dashboard/devices/${encodeURIComponent(item.device_id)}`;
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

function renderRecipientChips(container, project, draft) {
  container.replaceChildren();
  if (draft.recipients.size === 0) {
    const empty = element("p", "No recipients assigned");
    empty.className = "recipient-assignment-empty";
    const explanation = element(
      "p",
      project.configured
        ? "Alerts for this configured project policy will not have project recipients."
        : "No project recipients are configured. The existing fallback remains active until you save this project policy.",
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
    remove.setAttribute("aria-label", `Remove ${user?.name || address}`);
    remove.addEventListener("click", () => {
      draft.recipients.delete(address);
      markNotificationDraftUnsaved();
    });
    recipientChip.append(identity, remove);
    container.append(recipientChip);
  }
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
  projectSelect.addEventListener("change", () => {
    if (projectSelect.value === selectedNotificationProjectId) return;
    if (notificationDraftIsDirty(draft)) {
      notificationSaveState = "unsaved";
      notificationSaveMessage = "Unsaved changes";
      renderNotificationProjects();
      return;
    }
    selectedNotificationProjectId = projectSelect.value;
    notificationDraft = null;
    notificationSaveState = "unchanged";
    notificationSaveMessage = "No changes.";
    renderNotificationProjects();
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
  recipientSelect.disabled = !notificationDirectoryAvailable || eligibleUsers.length === 0;
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
  save.disabled = notificationSaveInFlight;
  save.addEventListener("click", async () => {
    if (notificationSaveInFlight) return;
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
  discard.disabled = notificationSaveInFlight || !notificationDraftIsDirty(draft);
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
    const actions = document.createElement("div");
    actions.className = "deployment-card__actions";
    const isReady = deployment.state === "PENDING";
    const download = element("button", "Agent Package");
    download.type = "button";
    download.className = "sb-button--primary";
    download.disabled = !isReady || deploymentRelease === null;
    download.addEventListener("click", () => window.location.assign("/api/v1/agent-releases/current/download"));
    const copyInstructions = element("button", "Copy Instruction");
    copyInstructions.type = "button";
    copyInstructions.className = "sb-button--secondary";
    copyInstructions.disabled = !isReady || deploymentRelease === null;
    copyInstructions.addEventListener("click", () => navigator.clipboard.writeText(installationInstructions(deploymentRelease)).catch(() => { deploymentsStatus.textContent = "Installation instructions could not be copied."; }));
    actions.append(download, copyInstructions);
    card.append(heading, actions);
    deploymentsList.append(card);
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
      deploymentsStatus.textContent = "Approved agent package unavailable.";
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
  document.getElementById("log-watch-offline").hidden = device.state !== "OFFLINE";
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

async function requestDeviceLogs(deviceId) {
  const response = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/logs?limit=60`, {
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("device logs request failed");
  return response.json();
}

function renderDeviceLogs(payload) {
  const container = document.getElementById("log-watch-sources");
  const labels = { skybeat_agent: "SkyBeat Agent", system_journal: "System Journal", kernel: "Kernel / dmesg" };
  const states = { available: "Available", permission_unavailable: "Permission unavailable", collection_error: "Collection error", no_report: "No report yet" };
  container.replaceChildren();
  for (const source of payload.sources ?? []) {
    if (!Object.hasOwn(labels, source.source)) continue;
    const card = document.createElement("section");
    card.className = "device-log-source";
    const heading = element("h4", labels[source.source]);
    const state = element("p", states[source.status] ?? "Unavailable");
    const stateClass = Object.hasOwn(states, source.status)
      ? source.status.replaceAll("_", "-")
      : "unavailable";
    state.className = `device-log-source__state device-log-source__state--${stateClass}`;
    card.append(heading, state);
    const entries = (payload.items ?? []).filter((item) => item.source === source.source);
    if (!entries.length) card.append(element("p", "No stored logs received for this source."));
    else {
      const list = document.createElement("ol");
      list.className = "device-log-entries";
      for (const entry of entries) {
        const row = document.createElement("li");
        const metadata = element("span", `${formatRelativeTime(entry.occurred_at ?? entry.received_at)}${entry.severity ? ` · ${entry.severity}` : ""}`);
        metadata.className = "device-log-entry__meta";
        const message = element("p", entry.message);
        message.className = "device-log-entry__message";
        row.append(metadata, message);
        list.append(row);
      }
      card.append(list);
    }
    container.append(card);
  }
  document.getElementById("log-watch-status").textContent = "Recent stored logs loaded.";
}

async function refreshDeviceDetailPage() {
  if (refreshing) return;
  refreshing = true;
  const deviceId = deviceDetailPage.dataset.deviceId;
  const now = Date.now();
  const fetchLogs = now - lastLogAttemptAt >= (document.hidden ? 60000 : 30000);
  if (fetchLogs) lastLogAttemptAt = now;
  try {
    const [deviceResult, logsResult] = await Promise.allSettled([
      requestDeviceDetail(deviceId),
      fetchLogs ? requestDeviceLogs(deviceId) : Promise.resolve(null),
    ]);
    if (deviceResult.status === "fulfilled") {
      renderDeviceDetailPage(deviceResult.value);
      document.getElementById("device-page-status").textContent = "Current device state loaded.";
      markDashboardFresh(deviceResult.value.server_time ?? new Date().toISOString());
    } else {
      document.getElementById("device-page-status").textContent = "Device status refresh failed. Last successful state is retained.";
      markDashboardStale();
    }
    if (fetchLogs) {
      if (logsResult.status === "fulfilled") renderDeviceLogs(logsResult.value);
      else document.getElementById("log-watch-status").textContent = "Recent log refresh failed. Last successful logs are retained.";
    }
  } catch (_) {
    document.getElementById("device-page-status").textContent = "Device refresh failed. Last successful state is retained.";
    markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
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
    typeof release?.wheel_filename !== "string" ||
    typeof release?.wheel_sha256 !== "string" ||
    typeof release?.archive_filename !== "string" ||
    typeof release?.archive_root !== "string" ||
    typeof release?.server_url !== "string"
  ) throw new Error("agent release response was invalid");
  return release;
}

function installationInstructions(release) {
  const insecureFlag = release.allow_insecure_local_server === true ? " --allow-insecure-local-server" : "";
  return `unzip ${release.archive_filename}\ncd ${release.archive_root}\nchmod +x ./install-agent.sh\nsudo ./install-agent.sh --server ${release.server_url} --package ./${release.wheel_filename} --sha256 ${release.wheel_sha256} --wheelhouse ./wheelhouse --lockfile ./requirements.lock --token-file ./enrollment.token${insecureFlag}`;
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
