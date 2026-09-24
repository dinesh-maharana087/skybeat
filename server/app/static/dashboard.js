"use strict";

const DEFAULT_PAGE_LIMIT = 50;
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const VISIBLE_REFRESH_MS = 15000;
const HIDDEN_REFRESH_MS = 60000;
const SEARCH_DEBOUNCE_MS = 250;
const HISTORY_RANGES = ["1h", "6h", "24h", "7d"];
const HISTORY_COLORS = ["#0b63ce", "#7a3ec8", "#007f6d", "#b54708"];
const dashboardView = document.body.dataset.dashboardView;
const SIDEBAR_PREFERENCE_KEY = "skybeat.sidebar.v1";
const appShell = document.querySelector(".app-shell");
const sidebarToggle = document.getElementById("sidebar-toggle");

const devices = document.getElementById("devices");
const deviceEmpty = document.getElementById("device-empty");
const deviceError = document.getElementById("device-error");
const refreshStatus = document.getElementById("refresh-status");
const lastRefresh = document.getElementById("last-refresh");
const staleWarning = document.getElementById("dashboard-stale-warning");
const overviewCards = document.getElementById("overview-cards");
const overviewStatus = document.getElementById("overview-status");
const awaitingFirstHeartbeat = document.getElementById("awaiting-first-heartbeat");
const overviewHealthMeter = document.getElementById("overview-health-meter");
const overviewHealthMeterFill = document.getElementById("overview-health-meter-fill");
const overviewHealthMeterLabel = document.getElementById("overview-health-meter-label");
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
const detailTitle = document.getElementById("detail-title");
const detailStatus = document.getElementById("detail-status");
const detailRetry = document.getElementById("detail-retry");
const detailClose = document.getElementById("detail-close");
const detailIdentity = document.getElementById("detail-identity");
const detailFreshness = document.getElementById("detail-freshness");
const detailSystem = document.getElementById("detail-system");
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
const enrollGpuEnabled = document.getElementById("enroll-gpu-enabled");
const enrollGpuCount = document.getElementById("enroll-gpu-count");
const enrollmentStatus = document.getElementById("enrollment-status");
const enrollmentCredentialPanel = document.getElementById("enrollment-credential-panel");
const enrollmentCredentialNode = document.getElementById("enrollment-credential");
const copyEnrollmentCredentialButton = document.getElementById("copy-enrollment-credential");
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

let refreshTimer = null;
let searchTimer = null;
let refreshing = false;
let loadingDevices = false;
let nextCursor = null;
let cursorHistory = [null];
let pageIndex = 0;
let lastSuccessfulRefresh = null;
let overviewTotal = null;
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
  const node = element("span", displayValue(value));
  node.className = `status-pill status-${displayValue(value).toLowerCase().replaceAll("_", "-")}`;
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

function setSidebarCollapsed(collapsed) {
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle?.setAttribute("aria-expanded", String(!collapsed));
  if (sidebarToggle !== null) {
    sidebarToggle.textContent = collapsed ? "Expand" : "Collapse";
    sidebarToggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
  }
  localStorage.setItem(SIDEBAR_PREFERENCE_KEY, collapsed ? "collapsed" : "expanded");
}

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
  if (!response.ok) throw new Error("dashboard management request failed");
  return responsePayload;
}

function renderOverview(payload) {
  const counts = payload.counts ?? {};
  overviewTotal = typeof counts.total === "number" ? counts.total : null;
  const cards = [
    ["Total Devices", counts.total],
    ["Online", counts.online],
    ["Suspect", counts.suspect],
    ["Offline", counts.offline],
    ["GPU Problems", counts.gpu_problem],
    ["Active Incidents", counts.active_incident],
  ];
  const nodes = cards.map(([label, value]) => {
    const card = document.createElement("article");
    card.className = "overview-card";
    card.append(element("h3", label), element("p", displayValue(value)));
    return card;
  });
  overviewCards?.replaceChildren(...nodes);
  const total = typeof counts.total === "number" && counts.total > 0 ? counts.total : 0;
  const online = typeof counts.online === "number" && counts.online > 0 ? counts.online : 0;
  const percentage = total === 0 ? 0 : Math.round((online / total) * 100);
  const healthText = total === 0 ? "0 / 0 devices online" : `${online} / ${total} devices online (${percentage}%)`;
  if (overviewHealthMeter !== null) overviewHealthMeter.setAttribute("aria-label", healthText);
  if (overviewHealthMeterFill !== null) overviewHealthMeterFill.style.width = `${percentage}%`;
  if (overviewHealthMeterLabel !== null) overviewHealthMeterLabel.textContent = healthText;
  if (awaitingFirstHeartbeat !== null) {
    awaitingFirstHeartbeat.textContent = `Awaiting first heartbeat: ${displayValue(
      counts.awaiting_first_heartbeat
    )}`;
  }
  if (overviewStatus !== null) {
    overviewStatus.textContent = `Overview updated ${formatRelativeTime(payload.server_time)}`;
    setExactTimestamp(overviewStatus, payload.server_time);
  }
  renderAttention(payload.attention);
  renderProjects(payload.projects, payload.projects_truncated === true);
}

function renderAttention(items) {
  if (overviewAttention === null) return;
  const attentionItems = Array.isArray(items) ? items : [];
  if (!attentionItems.length) {
    overviewAttention.replaceChildren(element("p", "No devices currently require attention."));
    return;
  }
  const list = document.createElement("ul");
  list.className = "attention-list";
  for (const item of attentionItems) {
    const row = document.createElement("li");
    row.append(
      element("strong", displayValue(item.name)),
      statusPill(item.state),
      statusPill(item.gpu_health?.effective),
      element("span", displayValue(item.project?.name)),
      timestampNode(item.last_seen_at)
    );
    if (item.has_active_incident === true) row.append(element("span", "Active incident"));
    list.append(row);
  }
  overviewAttention.replaceChildren(list);
}

function renderRecentIncidents(items) {
  if (overviewIncidents === null) return;
  const incidentItems = Array.isArray(items) ? items : [];
  overviewIncidents.replaceChildren(
    ...incidentItems.map((item) =>
      element(
        "p",
        `${displayValue(item.type)} · ${displayValue(item.device_name)} · ${displayValue(item.status)}`
      )
    )
  );
  if (!incidentItems.length) overviewIncidents.replaceChildren(element("p", "No recent incidents."));
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
  const headers = [
    "Project",
    "Device",
    "Hostname",
    "Availability",
    "Last Seen",
    "CPU",
    "Memory",
    "GPU Health",
    "GPU Count",
    "Primary IP",
    "Agent Version",
    "Latest Telemetry",
  ];
  const row = document.createElement("tr");
  for (const name of headers) {
    const cell = document.createElement("th");
    const filterName = {
      Project: "project_id",
      Availability: "state",
      "GPU Health": "gpu_state",
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

function deviceRow(item) {
  const row = document.createElement("tr");
  if (item.telemetry_stale === true) row.classList.add("telemetry-stale");
  row.append(element("td", displayValue(item.project?.name)));
  const deviceCell = document.createElement("td");
  const detailButton = element("button", displayValue(item.name));
  detailButton.type = "button";
  detailButton.ariaLabel = `View details for ${displayValue(item.name)}`;
  detailButton.addEventListener("click", () => openDetail(item.device_id, detailButton));
  deviceCell.append(detailButton);
  row.append(deviceCell);
  row.append(element("td", displayValue(item.hostname)));
  const availability = document.createElement("td");
  availability.append(statusPill(item.state));
  row.append(availability);
  const lastSeen = document.createElement("td");
  lastSeen.append(timestampNode(item.last_seen_at));
  row.append(lastSeen);
  row.append(element("td", formatPercent(item.cpu?.utilization_percent)));
  row.append(element("td", formatPercent(item.memory?.utilization_percent)));
  const gpuHealth = document.createElement("td");
  gpuHealth.append(statusPill(item.gpu_health?.effective));
  row.append(gpuHealth);
  row.append(element("td", displayValue(item.gpu_count)));
  row.append(element("td", displayValue(item.primary_ip)));
  row.append(element("td", displayValue(item.agent_version)));
  const latestTelemetry = document.createElement("td");
  latestTelemetry.append(timestampNode(item.latest_received_at));
  row.append(latestTelemetry);
  return row;
}

function renderDevices(items, { append = false } = {}) {
  const deviceItems = Array.isArray(items) ? items : [];
  const scrollTop = devices.scrollTop;
  let table = append ? document.getElementById("device-status-table") : null;
  if (!append) devices.replaceChildren();
  if (!deviceItems.length && !append) {
    const noDevices = overviewTotal === 0;
    deviceEmpty.textContent = noDevices
      ? "No devices have been enrolled."
      : "No devices match the current filters.";
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
  ];
  for (const [label, value, name] of values) {
    if (!value || value === "All projects") continue;
    const chip = element("button", `${label}: ${value} ×`);
    chip.type = "button";
    chip.ariaLabel = `Remove ${label} filter`;
    chip.addEventListener("click", () => {
      applyDeviceFilter(name, "");
    });
    activeFilters.append(chip);
  }
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
  lastRefresh.textContent = `Live updates - updated ${formatRelativeTime(serverTime)}.`;
  setExactTimestamp(lastRefresh, serverTime);
  setVisible(staleWarning, false);
}

function applyDevicePayload(payload, { append = false } = {}) {
  clearDeviceMessages();
  renderDevices(payload.items, { append });
  nextCursor = typeof payload.next_cursor === "string" ? payload.next_cursor : null;
  updateLoadMore();
  renderActiveFilters();
  refreshStatus.textContent = `Device list updated ${displayValue(payload.server_time)}`;
}

async function reloadDevices() {
  if (refreshing || loadingDevices) return;
  loadingDevices = true;
  resetDevicePagination();
  devices.replaceChildren();
  clearDeviceMessages();
  updateLoadMore();
  refreshStatus.textContent = "Loading current device status…";
  try {
    applyDevicePayload(await requestDevices(currentCursor()));
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    updateLoadMore();
  }
}

async function nextDevicePage() {
  if (refreshing || loadingDevices || !nextCursor) return;
  cursorHistory = cursorHistory.slice(0, pageIndex + 1);
  cursorHistory.push(nextCursor);
  pageIndex += 1;
  loadingDevices = true;
  updateLoadMore();
  try {
    applyDevicePayload(await requestDevices(currentCursor()));
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    updateLoadMore();
  }
}

async function previousDevicePage() {
  if (loadingDevices || pageIndex === 0) return;
  pageIndex -= 1;
  loadingDevices = true;
  try {
    applyDevicePayload(await requestDevices(currentCursor()));
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
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
    const [projectsResult, devicesResult] = await Promise.allSettled([
      requestProjects(),
      requestDevices(refreshCursor),
    ]);
    const projectsSucceeded = projectsResult.status === "fulfilled";
    const devicesSucceeded = devicesResult.status === "fulfilled";
    if (projectsSucceeded) renderProjects(projectsResult.value.items, false);
    if (devicesSucceeded && currentCursor() === refreshCursor && pageIndex === refreshPageIndex) {
      applyDevicePayload(devicesResult.value);
    }
    else showDeviceError();
    if (projectsSucceeded && devicesSucceeded) {
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
      markDashboardStale();
      return;
    }
    markDashboardFresh(overviewResult.value.server_time);
  } catch (_) {
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

async function refreshActiveView() {
  if (dashboardView === "devices") return refreshDashboard();
  if (dashboardView === "projects") return refreshProjectsView();
  return refreshOverviewView();
}

function detailPairs(target, pairs) {
  target.replaceChildren();
  for (const [label, value] of pairs) {
    target.append(element("dt", label), element("dd", displayValue(value)));
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
    detailIdentity,
    detailFreshness,
    detailSystem,
    detailPolicy,
    detailStorage,
    detailGpus,
    detailIncidents,
  ]) {
    target.replaceChildren();
  }
  currentDetail = null;
  detailManagementActions.hidden = true;
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
  detailManagementActions.hidden = false;
  detailTitle.textContent = `Device detail: ${displayValue(device.name)}`;
  detailPairs(detailIdentity, [
    ["Device name", device.name],
    ["Device UUID", device.device_id],
    ["Project", device.project?.name],
    ["Monitoring", device.monitoring_enabled === true ? "Enabled" : "Disabled"],
    ["Availability", device.state],
    ["GPU health", device.gpu_health?.effective],
  ]);
  detailPairs(detailFreshness, [
    ["Latest telemetry receipt", device.latest_received_at],
    ["Last seen", device.last_seen_at],
    ["Telemetry freshness", device.telemetry_stale === true ? "STALE" : "Current"],
  ]);
  const os = device.os ?? {};
  detailPairs(detailSystem, [
    ["Hostname", device.hostname],
    ["Primary IP", device.primary_ip],
    ["IP addresses", Array.isArray(device.ip_addresses) ? device.ip_addresses.join(", ") : null],
    ["Operating system", os.name],
    ["Architecture", os.architecture],
    ["Agent version", device.agent_version],
    ["Uptime", device.uptime_seconds],
    ["CPU utilization", formatPercent(device.cpu?.utilization_percent)],
    ["Memory utilization", formatPercent(device.memory?.utilization_percent)],
  ]);
  renderStorage(device.disks);
  renderGpus(device.gpus);
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
    card.append(values);
    list.append(card);
  }
  detailStorage.replaceChildren(list);
}

function renderGpus(gpus) {
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
      ["Utilization", formatPercent(gpu.utilization_percent)],
      ["Temperature", formatTemperature(gpu.temperature_celsius)],
      ["Memory used", formatBytes(gpu.memory_used_bytes)],
      ["Memory total", formatBytes(gpu.memory_total_bytes)],
    ]);
    card.append(values);
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
    const color = HISTORY_COLORS[index % HISTORY_COLORS.length];
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
      marker.style.backgroundColor = HISTORY_COLORS[index % HISTORY_COLORS.length];
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
    gpuMonitoringEnabled: enrollGpuEnabled.checked,
    expectedGpuMinCount: enrollGpuCount.value,
  };
}

function clearEnrollmentCredential() {
  enrollmentCredential = null;
  enrollmentCredentialNode.textContent = "";
  enrollmentCredentialPanel.hidden = true;
  copyEnrollmentCredentialButton.disabled = true;
}

function syncEnrollmentGpuPolicy() {
  if (!enrollGpuEnabled.checked) {
    enrollGpuCount.value = "0";
    enrollGpuCount.disabled = true;
    return;
  }
  enrollGpuCount.disabled = false;
  if (enrollGpuCount.value === "0") enrollGpuCount.value = "1";
}

function openEnrollmentDialog(draft = null) {
  deviceEnrollForm.reset();
  if (draft !== null) {
    enrollName.value = draft.name;
    enrollProject.value = draft.projectId;
    enrollGpuEnabled.checked = draft.gpuMonitoringEnabled;
    enrollGpuCount.value = draft.expectedGpuMinCount;
  }
  syncEnrollmentGpuPolicy();
  clearEnrollmentCredential();
  enrollmentStatus.textContent = "";
  enrollSubmit.disabled = false;
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
  } catch (_) {
    projectStatus.textContent = "Project could not be created. Check the name and try again.";
  } finally {
    projectSubmissionInFlight = false;
    projectSubmit.disabled = false;
  }
}

async function submitEnrollment() {
  if (enrollmentSubmissionInFlight || enrollmentCredential !== null) return;
  const name = enrollName.value.trim();
  const projectId = enrollProject.value;
  const gpuMonitoringEnabled = enrollGpuEnabled.checked;
  const expectedGpuMinCount = Number(enrollGpuCount.value);
  if (!name || !projectId || !Number.isInteger(expectedGpuMinCount)) {
    enrollmentStatus.textContent = "Enter a device name, choose a project, and set the expected GPU count.";
    return;
  }
  enrollmentSubmissionInFlight = true;
  enrollSubmit.disabled = true;
  enrollmentStatus.textContent = "Enrolling device…";
  try {
    const payload = await requestDashboardMutation("/api/v1/devices", "POST", {
      name,
      project_id: projectId,
      gpu_monitoring_enabled: gpuMonitoringEnabled,
      expected_gpu_min_count: gpuMonitoringEnabled ? expectedGpuMinCount : 0,
    });
    if (typeof payload?.credential !== "string" || !payload.credential.startsWith("sb1.")) {
      throw new Error("credential response was invalid");
    }
    enrollmentCredential = payload.credential;
    enrollmentCredentialNode.textContent = enrollmentCredential;
    enrollmentCredentialPanel.hidden = false;
    copyEnrollmentCredentialButton.disabled = false;
    enrollmentStatus.textContent = "Device enrolled. Copy the credential before closing this dialog.";
    await refreshCanonicalDashboard();
  } catch (_) {
    enrollmentStatus.textContent = "Device could not be enrolled. Check the form and try again.";
    enrollSubmit.disabled = false;
  } finally {
    enrollmentSubmissionInFlight = false;
  }
}

async function copyEnrollmentCredential() {
  if (enrollmentCredential === null) return;
  try {
    await navigator.clipboard.writeText(enrollmentCredential);
    enrollmentStatus.textContent = "Credential copied. Store it only in the protected agent environment file.";
  } catch (_) {
    enrollmentStatus.textContent = "Credential could not be copied. Copy it manually before closing this dialog.";
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
  if (deviceEnrollDialog.open) deviceEnrollDialog.close();
}

function closeMoveDialog() {
  if (moveDeviceDialog.open) moveDeviceDialog.close();
}

function closeMonitoringDialog() {
  if (monitoringDialog.open) monitoringDialog.close();
}

if (dashboardView === "devices") {
const projectIdFromUrl = new URLSearchParams(window.location.search).get("project_id");
if (projectIdFromUrl !== null && CANONICAL_UUID.test(projectIdFromUrl)) {
  requestedProjectId = projectIdFromUrl;
}
const sidebarPreference = localStorage.getItem(SIDEBAR_PREFERENCE_KEY);
if (sidebarPreference === "collapsed") setSidebarCollapsed(true);
sidebarToggle?.addEventListener("click", () => {
  setSidebarCollapsed(!appShell?.classList.contains("sidebar-collapsed"));
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
detailClose.addEventListener("click", closeDetail);
newProject.addEventListener("click", () => openProjectDialog());
addDevice.addEventListener("click", () => openEnrollmentDialog());
newProjectFromEnroll.addEventListener("click", () => {
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
enrollGpuEnabled.addEventListener("change", syncEnrollmentGpuPolicy);
copyEnrollmentCredentialButton.addEventListener("click", () => void copyEnrollmentCredential());
deviceEnrollDialog.addEventListener("close", () => {
  clearEnrollmentCredential();
  deviceEnrollForm.reset();
  syncEnrollmentGpuPolicy();
});
detailChangeProject.addEventListener("click", openMoveDialog);
detailToggleMonitoring.addEventListener("click", openMonitoringConfirmation);
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
document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
  window.location.assign("/auth/google/login");
});
document.addEventListener("visibilitychange", () => {
  window.clearTimeout(refreshTimer);
  if (document.hidden) {
    if (!refreshing) scheduleRefresh();
    return;
  }
  refreshActiveView();
});
document.addEventListener("keydown", (event) => {
  const dialogOpen = projectDialog.open || deviceEnrollDialog.open || moveDeviceDialog.open || monitoringDialog.open;
  if (event.key === "Escape" && !dialogOpen && !detailPanel.hidden) closeDetail();
});

refreshActiveView();
} else {
  sidebarToggle?.addEventListener("click", () => {
    setSidebarCollapsed(!appShell?.classList.contains("sidebar-collapsed"));
  });
  document.getElementById("logout")?.addEventListener("click", async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/auth/google/login");
  });
  newProject?.addEventListener("click", () => openProjectDialog());
  projectForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitProject();
  });
  projectClose?.addEventListener("click", closeProjectDialog);
  projectCancel?.addEventListener("click", closeProjectDialog);
  projectDialog?.addEventListener("cancel", (event) => {
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
  refreshActiveView();
}
