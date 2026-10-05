"""Exercise the Devices table with a small safe DOM harness."""

import shutil
import subprocess
import textwrap
from pathlib import Path


def test_device_rows_keep_os_communication_gpu_and_text_safety_separate():
    source = (Path(__file__).resolve().parents[1] / "app/static/dashboard.js").read_text(
        encoding="utf-8"
    )
    harness = textwrap.dedent(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const snippets = [
          source.slice(source.indexOf("function tableHeader()"),
            source.indexOf("function filterOptions(")),
          source.slice(source.indexOf("function conciseOsLabel("),
            source.indexOf("function renderDevices(")),
        ].join("\\n");
        class Node {
          constructor(tag) {
            this.tag = tag;
            this.children = [];
            this.textContent = "";
            this.classes = [];
            this.dataset = {};
            this.classList = { add: (value) => this.classes.push(value) };
          }
          set innerHTML(_) { throw new Error("unsafe HTML insertion"); }
          append(...nodes) { this.children.push(...nodes); }
          addEventListener(name, handler) { this.handler = handler; }
          setAttribute(name, value) { this[name] = value; }
        }
        const document = { createElement: (tag) => new Node(tag) };
        const element = (tag, value) => {
          const node = document.createElement(tag);
          node.textContent = String(value);
          return node;
        };
        const displayValue = (value) => value == null || value === "" ? "—" : String(value);
        const statusPill = (value) => element("span", displayValue(value));
        const timestampNode = (value) => element("span", value ?? "Never");
        const opened = [];
        const context = { document, element, displayValue, statusPill, timestampNode,
          openDetail: (id) => opened.push(id) };
        vm.runInNewContext(snippets, context);
        const text = (node) => [node.textContent, ...node.children.map(text)].join(" ").trim();
        const headers = context.tableHeader().children[0].children[0].children
          .map(text).map((value) => value.replace(" ▾", "").trim());
        if (headers.join("|") !== "Device|Project|Status|OS|GPU|Last Seen|Attention") {
          throw new Error("unexpected table headers");
        }
        const base = {
          device_id: "device-1", name: "<Device>", hostname: "<host>",
          project: { name: "<Project>" }, state: "ONLINE",
          os: { name: "<Ubuntu>", version: "24.04" },
          gpu_health: { effective: "OK" }, latest_received_at: "now", last_seen_at: "now",
        };
        const online = context.deviceRow(base);
        if (online.children.length !== 7 || !text(online.children[0]).includes("<host>") ||
            text(online.children[3]) !== "<Ubuntu> 24.04" ||
            text(online.children[6]) !== "—" ||
            !text(online.children[1]).includes("<Project>")) {
          throw new Error("online row lost text or columns");
        }
        online.children[0].children[0].handler();
        if (opened.join() !== "device-1") throw new Error("device detail action is not available");
        const sameHost = context.deviceRow({ ...base, hostname: base.name });
        if (sameHost.children[0].children.length !== 1) {
          throw new Error("duplicate hostname rendered");
        }
        const offline = context.deviceRow({ ...base, state: "OFFLINE", os: null });
        if (text(offline.children[3]) !== "Not reported" ||
            !text(offline.children[6]).includes("Communication: OFFLINE") ||
            !offline.classes.includes("device-row--communication")) {
          throw new Error("offline row is unclear");
        }
        const suspect = context.deviceRow({ ...base, state: "SUSPECT", hostname: null });
        if (!text(suspect.children[6]).includes("Communication: SUSPECT") ||
            suspect.children[0].children.length !== 1) {
          throw new Error("suspect or missing-host row is unclear");
        }
        const gpu = context.deviceRow({ ...base, gpu_health: { effective: "DRIVER_ERROR" } });
        if (!text(gpu.children[6]).includes("GPU: DRIVER ERROR") ||
            text(gpu.children[6]).includes("Communication")) {
          throw new Error("GPU attention is conflated");
        }
        const awaiting = context.deviceRow({ ...base, latest_received_at: null,
          gpu_health: { effective: "UNKNOWN" }, os: {} });
        if (text(awaiting.children[6]) !== "—" || text(awaiting.children[3]) !== "Not reported") {
          throw new Error("missing telemetry became an incident");
        }
        """
    )
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(  # noqa: S603 - fixed local Node harness
        [node, "--input-type=module", "--eval", harness],
        input=source,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
