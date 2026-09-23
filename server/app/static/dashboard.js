"use strict";

const devices = document.getElementById("devices");
const status = document.getElementById("refresh-status");
const search = document.getElementById("search");
const state = document.getElementById("state");
let refreshTimer = null;
let refreshing = false;

function element(tag, text) {
  const node = document.createElement(tag);
  node.textContent = text ?? "—";
  return node;
}

function render(items) {
  devices.replaceChildren();
  if (!items.length) {
    devices.append(element("p", "No devices match the current filters."));
    return;
  }
  const table = document.createElement("table");
  const header = document.createElement("tr");
  ["Project", "Device", "Hostname", "State", "Last seen", "CPU", "RAM", "GPU"].forEach((name) =>
    header.append(element("th", name))
  );
  table.append(header);
  for (const item of items) {
    const row = document.createElement("tr");
    row.className = item.telemetry_stale ? "stale" : "";
    const gpu = item.gpu_health?.effective;
    const cells = [
      item.project?.name,
      item.hostname,
      item.state,
      item.last_seen_at,
      item.cpu?.utilization_percent == null ? null : `${item.cpu.utilization_percent}%`,
      item.memory?.utilization_percent == null ? null : `${item.memory.utilization_percent}%`,
      item.telemetry_stale ? `${gpu ?? "UNKNOWN"} (STALE)` : gpu,
    ];
    row.append(element("td", item.project?.name));
    const deviceCell = document.createElement("td");
    const detailButton = element("button", item.name);
    detailButton.type = "button";
    detailButton.addEventListener("click", () => showDetail(item.device_id));
    deviceCell.append(detailButton);
    row.append(deviceCell);
    cells.slice(1).forEach((value) => row.append(element("td", value)));
    table.append(row);
  }
  devices.append(table);
}

async function showDetail(deviceId) {
  const detail = document.getElementById("detail");
  detail.replaceChildren(element("p", "Loading device detail…"));
  try {
    const [deviceResponse, alertsResponse] = await Promise.all([
      fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}`, { credentials: "same-origin" }),
      fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/alerts`, { credentials: "same-origin" }),
    ]);
    if (!deviceResponse.ok || !alertsResponse.ok) throw new Error("detail request failed");
    const device = await deviceResponse.json();
    const alerts = await alertsResponse.json();
    const title = element("h2", device.name);
    const close = element("button", "Close detail");
    close.type = "button";
    close.addEventListener("click", () => detail.replaceChildren());
    const content = element("pre", JSON.stringify({ device, alerts: alerts.items }, null, 2));
    detail.replaceChildren(close, title, content);
  } catch (_) {
    detail.replaceChildren(element("p", "Unable to load device detail."));
  }
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  const query = new URLSearchParams({ limit: "100" });
  if (search.value.trim()) query.set("search", search.value.trim());
  if (state.value) query.set("state", state.value);
  try {
    const response = await fetch(`/api/v1/devices?${query}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error("dashboard refresh failed");
    const payload = await response.json();
    render(payload.items);
    status.textContent = `Updated ${payload.server_time}`;
  } catch (_) {
    status.textContent = "Unable to refresh. Displayed telemetry may be stale.";
  } finally {
    refreshing = false;
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refresh, document.hidden ? 60000 : 15000);
  }
}

for (const control of [search, state]) control.addEventListener("change", refresh);
document.getElementById("logout").addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST", credentials: "same-origin" });
  window.location.assign("/auth/google/login");
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
refresh();
