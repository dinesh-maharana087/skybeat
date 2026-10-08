"""Stage 12D keeps device routing inside the existing Alert Routing view."""

import shutil
import subprocess
import textwrap
from pathlib import Path


def test_device_routing_editor_is_integrated_with_project_routing():
    root = Path(__file__).parents[1] / "app"
    script = (root / "static" / "dashboard.js").read_text(encoding="utf-8")
    template = (root / "templates" / "dashboard.html").read_text(encoding="utf-8")
    styles = (root / "static" / "device-routing.css").read_text(encoding="utf-8")

    assert "Device overrides" in script
    assert "INHERITS PROJECT" in script
    assert "CUSTOM ROUTING" in script
    assert "Use project routing" in script
    assert "requestNotificationDevices" in script
    assert "notificationDeviceDraftIsDirty" in script
    assert "Save device routing" in script
    assert "device-routing-list" in script
    assert "alert-routing-device" in styles
    assert "/static/device-routing.css?v=stage12d" in template
    assert 'id="notifications-list"' in template
    assert "Device Notifications" not in template


def test_device_routing_editor_preserves_drafts_and_reloads_saved_server_state():
    node = shutil.which("node")
    assert node is not None
    script = (Path(__file__).parents[1] / "app" / "static" / "dashboard.js").read_text(
        encoding="utf-8"
    )
    harness = textwrap.dedent(
        """
        import fs from "node:fs";
        import vm from "node:vm";

        const source = fs.readFileSync(0, "utf8");
        const requestSource = source.slice(
          source.indexOf("async function requestNotificationDevices"),
          source.indexOf("async function requestToInstallDeployments"),
        );
        const routingSource = source.slice(
          source.indexOf("const ALERT_ROUTING_EVENTS"),
          source.indexOf("function deploymentStateLabel"),
        );
        const projectId = "11111111-1111-4111-8111-111111111111";
        const firstId = "22222222-2222-4222-8222-222222222222";
        const secondId = "33333333-3333-4333-8333-333333333333";
        const events = {
          device_offline_enabled: true, device_recovered_enabled: true,
          gpu_degraded_enabled: true, gpu_recovered_enabled: true,
        };
        const project = {
          project_id: projectId, project_name: "Warehouse A", configured: true,
          recipients: ["alice@example.test", "bob@example.test"], ...events,
        };
        const inherited = { recipients: [...project.recipients], ...events };
        const devices = [
          {
            device_id: firstId, device_name: "Device 1", project_id: projectId,
            project_name: project.project_name, mode: "INHERIT_PROJECT",
            effective: { ...inherited }, inherited: { ...inherited }, custom: null,
          },
          {
            device_id: secondId, device_name: "Device 2", project_id: projectId,
            project_name: project.project_name, mode: "CUSTOM",
            effective: { recipients: ["charlie@example.test"], ...events },
            inherited: { ...inherited },
            custom: { recipients: ["charlie@example.test"], ...events },
          },
        ];
        const mutations = [];
        let failNextSave = false;
        let holdNextSave = false;
        let releaseSave = null;
        let deviceReads = 0;
        const listeners = new WeakMap();
        class Element {
          constructor(tag = "") {
            this.tag = tag; this.id = ""; this.name = ""; this.value = "";
            this.textContent = ""; this.children = []; this.attributes = new Map();
            this.disabled = false; this.checked = false;
          }
          append(...items) { this.children.push(...items); }
          replaceChildren(...items) { this.children = items; }
          setAttribute(key, value) { this.attributes.set(key, String(value)); }
          getAttribute(key) { return this.attributes.get(key); }
          addEventListener(key, listener) {
            const entries = listeners.get(this) ?? new Map();
            entries.set(key, listener); listeners.set(this, entries);
          }
          emit(key) {
            return listeners.get(this)?.get(key)?.({ target: this, preventDefault() {} });
          }
        }
        const list = new Element("div");
        const status = new Element("p");
        function element(tag, value) {
          const item = new Element(tag); item.textContent = value; return item;
        }
        function descendants(item) {
          return item.children.flatMap((child) => [child, ...descendants(child)]);
        }
        function nodes() { return descendants(list); }
        function editorNodes() {
          const editor = nodes().find((item) => item.className === "alert-routing-device__editor");
          return [editor, ...descendants(editor)];
        }
        function text(value, items = nodes()) {
          return items.find((item) => item.textContent === value);
        }
        function row(name) {
          return nodes().find((item) => item.className === "alert-routing-device__row" &&
            item.children[0].textContent === name);
        }
        function response(payload) { return { ok: true, json: async () => payload }; }
        const context = {
          document: { createElement: (tag) => new Element(tag) }, element,
          notificationsList: list, notificationsStatus: status, refreshing: false,
          notificationProjects: [], selectedNotificationProjectId: null,
          notificationUsers: [], notificationDraft: null,
          notificationSaveState: "unchanged", notificationSaveMessage: "No changes.",
          notificationSaveInFlight: false, notificationDirectoryAvailable: true,
          notificationDevices: [], selectedNotificationDeviceId: null,
          notificationDeviceDraft: null, notificationDeviceSaveState: "unchanged",
          notificationDeviceSaveMessage: "No changes.", notificationDeviceSaveInFlight: false,
          notificationDeviceLoadState: "loading", notificationDeviceRequestId: 0,
          markDashboardFresh() {}, markDashboardStale() {}, encodeURIComponent,
          async requestNotifications() {
            return { items: [{ ...project, recipients: [...project.recipients] }] };
          },
          async requestUsers() {
            return { items: ["alice", "bob", "charlie", "david"].map((name) => ({
              name, email: `${name}@example.test`, active: true,
            })) };
          },
          async fetch(path) {
            if (path !== `/api/v1/notifications/${projectId}/devices`) throw new Error(path);
            deviceReads += 1;
            return response({ items: structuredClone(devices) });
          },
          async requestDashboardMutation(path, method, payload) {
            mutations.push({ path, method, payload });
            if (holdNextSave) {
              holdNextSave = false;
              await new Promise((resolve) => { releaseSave = resolve; });
            }
            if (failNextSave) { failNextSave = false; throw new Error("rejected"); }
            const device = devices.find((item) => path.endsWith(item.device_id));
            if (!device) throw new Error("wrong device");
            if (method === "PUT") {
              device.mode = "CUSTOM";
              device.custom = structuredClone(payload);
              device.effective = structuredClone(payload);
            } else if (method === "DELETE") {
              device.mode = "INHERIT_PROJECT";
              device.custom = null;
              device.effective = structuredClone(device.inherited);
            } else throw new Error("wrong method");
            return { notification: { mode: device.mode } };
          },
        };
        vm.runInNewContext(requestSource + routingSource, context);
        await context.refreshNotificationsView();
        if (!text("INHERITS PROJECT") || !text("CUSTOM ROUTING")) throw new Error("states missing");
        if (!text("This device currently uses Warehouse A routing.")) {
          throw new Error("inherit context missing");
        }
        if (!editorNodes().find(
          (item) => item.name === "device_offline_enabled" && item.disabled,
        )) {
          throw new Error("inherited event controls were editable");
        }
        if (editorNodes().some((item) => item.getAttribute("aria-label")?.startsWith("Remove"))) {
          throw new Error("inherited recipient was editable");
        }
        row("Device 2").emit("click");
        if (!text("charlie@example.test", editorNodes())) {
          throw new Error("custom recipient missing");
        }
        editorNodes().find(
          (item) => item.getAttribute("aria-label") === "Remove charlie",
        ).emit("click");
        if (!text("No recipients assigned", editorNodes())) {
          throw new Error("zero recipients missing");
        }
        row("Device 1").emit("click");
        if (!text("Save or discard device changes before switching devices.")) {
          throw new Error("dirty device switch was allowed");
        }
        const projectSelect = nodes().find((item) => item.id === "notification-project-select");
        projectSelect.value = "other-project";
        projectSelect.emit("change");
        if (!text("Save or discard device changes before switching projects.")) {
          throw new Error("dirty project switch was allowed");
        }
        failNextSave = true;
        await text("Save device routing", editorNodes()).emit("click");
        if (!text("Save failed. Your unsaved changes are still shown.")) {
          throw new Error("failed save did not keep draft");
        }
        if (!text("No recipients assigned", editorNodes())) throw new Error("failed draft lost");
        const select = editorNodes().find(
          (item) => item.id === "device-notification-recipient-select",
        );
        select.value = "david@example.test";
        text("Assign device recipient", editorNodes()).emit("click");
        const gpu = editorNodes().find((item) => item.name === "gpu_degraded_enabled");
        gpu.checked = false;
        gpu.emit("change");
        const readsBeforeSave = deviceReads;
        holdNextSave = true;
        const saving = text("Save device routing", editorNodes()).emit("click");
        if (!text("Save routing policy").disabled ||
          !editorNodes().find((item) => item.name === "gpu_degraded_enabled").disabled ||
          !editorNodes().find(
            (item) => item.id === "device-notification-recipient-select",
          ).disabled) {
          throw new Error("routing controls remained editable during save");
        }
        releaseSave();
        await saving;
        if (deviceReads <= readsBeforeSave || !text("Saved")) {
          throw new Error("saved state was not reloaded");
        }
        if (devices[1].custom.recipients.join() !== "david@example.test") {
          throw new Error("server did not receive custom recipient");
        }
        if (devices[1].custom.gpu_degraded_enabled !== false) {
          throw new Error("device event controls were not saved");
        }
        if (!text("david@example.test", editorNodes())) {
          throw new Error("server state not rendered");
        }
        editorNodes().find(
          (item) => item.name === "device-routing-mode" && item.value === "INHERIT_PROJECT",
        ).emit("change");
        if (devices[1].mode !== "CUSTOM" ||
          !text("This device will use Warehouse A routing after you select Use project routing.")) {
          throw new Error("pending reset was presented as already active");
        }
        await text("Use project routing", editorNodes()).emit("click");
        if (devices[1].mode !== "INHERIT_PROJECT" || devices[1].custom !== null) {
          throw new Error("reset did not remove override");
        }
        if (!text("This device currently uses Warehouse A routing.")) {
          throw new Error("project inheritance not restored");
        }
        row("Device 1").emit("click");
        editorNodes().find(
          (item) => item.name === "device-routing-mode" && item.value === "CUSTOM",
        ).emit("change");
        if (mutations.length !== 3) throw new Error("draft switch wrote an override");
        if (!text("alice@example.test", editorNodes()) ||
          !text("bob@example.test", editorNodes())) {
          throw new Error("new custom draft did not copy current effective policy");
        }
        text("Discard device changes", editorNodes()).emit("click");
        if (!text("This device currently uses Warehouse A routing.")) {
          throw new Error("discard did not restore inheritance");
        }
        """
    )
    result = subprocess.run(  # noqa: S603 - uses the locally discovered Node executable
        [node, "--input-type=module", "--eval", harness],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
