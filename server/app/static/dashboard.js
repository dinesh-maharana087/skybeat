"use strict";

const PAGE_LIMIT = 50;
const VISIBLE_REFRESH_MS = 15000;
const HIDDEN_REFRESH_MS = 60000;
const SEARCH_DEBOUNCE_MS = 250;

const devices = document.getElementById("devices");
const deviceEmpty = document.getElementById("device-empty");
const deviceError = document.getElementById("device-error");
const refreshStatus = document.getElementById("refresh-status");
const lastRefresh = document.getElementById("last-refresh");
const staleWarning = document.getElementById("dashboard-stale-warning");
const overviewCards = document.getElementById("overview-cards");
const overviewStatus = document.getElementById("overview-status");
const awaitingFirstHeartbeat = document.getElementById("awaiting-first-heartbeat");
const projectSummary = document.getElementById("project-summary-content");
const projectFilter = document.getElementById("project-filter");
const stateFilter = document.getElementById("state-filter");
const gpuStateFilter = document.getElementById("gpu-state-filter");
const search = document.getElementById("search");
const includeDisabled = document.getElementById("include-disabled");
const filters = document.getElementById("filters");
const resetFilters = document.getElementById("reset-filters");
const loadMore = document.getElementById("load-more");
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

let refreshTimer = null;
let searchTimer = null;
let refreshing = false;
let loadingDevices = false;
let nextCursor = null;
let overviewTotal = null;
let selectedDeviceId = null;
let detailGeneration = 0;
let detailAbortController = null;
let detailLastSuccess = null;
let detailOrigin = null;

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

function setVisible(node, visible) {
  node.hidden = !visible;
}

function clearDeviceMessages() {
  setVisible(deviceEmpty, false);
  setVisible(deviceError, false);
}

function deviceQuery(cursor = null) {
  const query = new URLSearchParams({ limit: String(PAGE_LIMIT) });
  if (projectFilter.value) query.set("project_id", projectFilter.value);
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
  overviewCards.replaceChildren(...nodes);
  awaitingFirstHeartbeat.textContent = `Awaiting first heartbeat: ${displayValue(
    counts.awaiting_first_heartbeat
  )}`;
  overviewStatus.textContent = `Overview updated ${displayValue(payload.server_time)}`;
  renderProjects(payload.projects, payload.projects_truncated === true);
}

function renderProjects(projects, truncated) {
  const selectedProject = projectFilter.value;
  const projectItems = Array.isArray(projects) ? projects : [];
  projectFilter.replaceChildren(element("option", "All projects"));
  projectFilter.firstChild.value = "";
  const summary = document.createElement("ul");
  summary.className = "project-list";
  for (const project of projectItems) {
    const option = element("option", displayValue(project.name));
    option.value = displayValue(project.project_id);
    if (option.value === selectedProject) option.selected = true;
    projectFilter.append(option);

    const counts = project.device_counts ?? {};
    const item = document.createElement("li");
    item.append(
      element("strong", displayValue(project.name)),
      element(
        "span",
        `Total ${displayValue(counts.total)} · Online ${displayValue(counts.online)} · ` +
          `Suspect ${displayValue(counts.suspect)} · Offline ${displayValue(counts.offline)} · ` +
          `Awaiting ${displayValue(counts.awaiting_first_heartbeat)}`
      )
    );
    summary.append(item);
  }
  if (!projectItems.length) {
    projectSummary.replaceChildren(element("p", "No projects are available."));
    return;
  }
  if (truncated) summary.append(element("li", "Additional projects are not shown."));
  projectSummary.replaceChildren(summary);
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
  for (const name of headers) row.append(element("th", name));
  const head = document.createElement("thead");
  head.append(row);
  table.append(head, document.createElement("tbody"));
  return table;
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
  const values = [
    item.hostname,
    item.state,
    item.last_seen_at,
    formatPercent(item.cpu?.utilization_percent),
    formatPercent(item.memory?.utilization_percent),
    item.gpu_health?.effective,
    item.gpu_count,
    item.primary_ip,
    item.agent_version,
    item.latest_received_at,
  ];
  for (const value of values) row.append(element("td", displayValue(value)));
  return row;
}

function renderDevices(items, { append = false } = {}) {
  const deviceItems = Array.isArray(items) ? items : [];
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
}

function updateLoadMore() {
  loadMore.disabled = loadingDevices;
  setVisible(loadMore, typeof nextCursor === "string" && nextCursor.length > 0);
}

function showDeviceError() {
  deviceError.textContent = "Unable to refresh the device list. Displayed device data was retained.";
  setVisible(deviceError, true);
}

function markDashboardStale() {
  staleWarning.textContent = "Dashboard data may be stale — refresh failed.";
  setVisible(staleWarning, true);
}

function markDashboardFresh(serverTime) {
  lastRefresh.textContent = `Last successful refresh: ${displayValue(serverTime)}`;
  setVisible(staleWarning, false);
}

function applyDevicePayload(payload, { append = false } = {}) {
  clearDeviceMessages();
  renderDevices(payload.items, { append });
  nextCursor = typeof payload.next_cursor === "string" ? payload.next_cursor : null;
  updateLoadMore();
  refreshStatus.textContent = `Device list updated ${displayValue(payload.server_time)}`;
}

async function reloadDevices() {
  if (refreshing || loadingDevices) return;
  loadingDevices = true;
  nextCursor = null;
  devices.replaceChildren();
  clearDeviceMessages();
  updateLoadMore();
  refreshStatus.textContent = "Loading current device status…";
  try {
    applyDevicePayload(await requestDevices());
  } catch (_) {
    showDeviceError();
    markDashboardStale();
  } finally {
    loadingDevices = false;
    updateLoadMore();
  }
}

async function loadMoreDevices() {
  if (refreshing || loadingDevices || !nextCursor) return;
  loadingDevices = true;
  updateLoadMore();
  try {
    applyDevicePayload(await requestDevices(nextCursor), { append: true });
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
  refreshTimer = window.setTimeout(refreshDashboard, document.hidden ? 60000 : 15000);
}

async function refreshDashboard() {
  if (refreshing || loadingDevices) {
    if (!refreshing) scheduleRefresh();
    return;
  }
  refreshing = true;
  refreshStatus.textContent = "Refreshing dashboard…";
  try {
    const [overviewResult, devicesResult] = await Promise.allSettled([
      requestOverview(),
      requestDevices(),
    ]);
    const overviewSucceeded = overviewResult.status === "fulfilled";
    const devicesSucceeded = devicesResult.status === "fulfilled";
    if (overviewSucceeded) renderOverview(overviewResult.value);
    else overviewStatus.textContent = "Unable to refresh overview. Displayed overview data was retained.";
    if (devicesSucceeded) applyDevicePayload(devicesResult.value);
    else showDeviceError();
    if (overviewSucceeded && devicesSucceeded) {
      markDashboardFresh(devicesResult.value.server_time);
      await refreshOpenDetail();
    } else markDashboardStale();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
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
  selectedDeviceId = null;
  detailLastSuccess = null;
  detailPanel.hidden = true;
  detailStatus.textContent = "";
  detailRetry.hidden = true;
  const origin = detailOrigin;
  detailOrigin = null;
  if (origin?.isConnected) origin.focus();
}

filters.addEventListener("submit", (event) => {
  event.preventDefault();
  reloadDevices();
});
for (const control of [projectFilter, stateFilter, gpuStateFilter, includeDisabled]) {
  control.addEventListener("change", () => reloadDevices());
}
search.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(reloadDevices, SEARCH_DEBOUNCE_MS);
});
resetFilters.addEventListener("click", () => {
  filters.reset();
  reloadDevices();
});
loadMore.addEventListener("click", loadMoreDevices);
detailClose.addEventListener("click", closeDetail);
detailRetry.addEventListener("click", () => {
  if (selectedDeviceId !== null) void loadDetail(selectedDeviceId, { focus: true });
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
  refreshDashboard();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !detailPanel.hidden) closeDetail();
});

refreshDashboard();
