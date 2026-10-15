"""Deployment cards follow the active artifact and keep downloads pinned."""

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


def run_dashboard_harness(harness: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    source = (Path(__file__).resolve().parents[1] / "app/static/dashboard.js").read_text(
        encoding="utf-8"
    )
    result = subprocess.run(  # noqa: S603 - fixed local source and test harness
        [node, "--input-type=module", "--eval", textwrap.dedent(harness)],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_card_version_refresh_and_pinned_download_keep_enrollment_unchanged():
    run_dashboard_harness(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("function deploymentStateLabel"),
          source.indexOf("async function requestRegisteredReleases"),
        );
        const node = (tag, text = "") => ({
          tag, textContent: text, children: [], disabled: false, hidden: false,
          append(...children) { this.children.push(...children); },
          replaceChildren(...children) { this.children = children; },
          setAttribute(name, value) { this[name] = value; },
          addEventListener(name, handler) { this[name] = handler; },
        });
        const list = node("list");
        const empty = node("empty");
        const redirects = [];
        const enrollment = { enrollment_id: "unchanged", device_name: "GPU node",
          project_name: "Production", state: "PENDING" };
        const context = {
          document: { createElement: (tag) => node(tag), createElementNS: (_, tag) => node(tag) },
          element: node, statusPill: (value) => node("status", value),
          deploymentsList: list, deploymentsEmpty: empty,
          toInstallDeployments: [enrollment], deploymentRelease: null,
          openDeploymentDeleteDialog() {}, deploymentDeleteIcon: () => node("icon"),
          window: { location: { assign: (url) => redirects.push(url) } },
          navigator: { clipboard: { writeText: async () => {} } },
          installationInstructions: () => "instructions", deploymentsStatus: node("status"),
        };
        const render = vm.runInNewContext(`${code}\nrenderDeployments`, context);
        const card = () => list.children[0];
        const actions = () => card().children[2].children;
        render();
        if (card().children[1].textContent !== "Agent version: Not available" ||
            !actions()[0].disabled || !actions()[1].disabled) {
          throw new Error("unapproved release enabled installation");
        }
        context.deploymentRelease = { version: "1.0.5", archive_sha256: "a".repeat(64) };
        render();
        if (card().children[1].textContent !== "Agent version: v1.0.5" ||
            actions()[0].disabled || actions()[1].disabled) {
          throw new Error("active version was not shown");
        }
        actions()[0].click();
        if (!redirects[0].endsWith("archive_sha256=" + "a".repeat(64))) {
          throw new Error("download was not pinned to shown release");
        }
        context.deploymentRelease = { version: "1.0.6", archive_sha256: "b".repeat(64) };
        render();
        actions()[0].click();
        if (card().children[1].textContent !== "Agent version: v1.0.6" ||
            !redirects[1].endsWith("archive_sha256=" + "b".repeat(64)) ||
            enrollment.enrollment_id !== "unchanged") {
          throw new Error("new approval did not refresh card without editing enrollment");
        }
        enrollment.state = "EXPIRED";
        render();
        if (!actions()[0].disabled || !actions()[1].disabled ||
            card().children[0].children[1].children[0].textContent !== "TOKEN EXPIRED") {
          throw new Error("expired enrollment could install");
        }
        """
    )


def test_copied_instruction_checks_the_same_immutable_archive_digest():
    run_dashboard_harness(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("async function requestReleaseMetadata()"),
          source.indexOf("function downloadEnrollmentToken()"),
        );
        const release = {
          version: "1.0.6", archive_sha256: "b".repeat(64),
          archive_filename: "skybeat-agent-1.0.6-linux.zip", archive_root: "skybeat-agent-1.0.6",
          wheel_filename: "skybeat_agent-1.0.6-py3-none-any.whl",
          wheel_sha256: "c".repeat(64), server_url: "https://monitor.example.test",
          allow_insecure_local_server: false,
        };
        const context = { fetch: async () => ({ ok: true, json: async () => ({ release }) }) };
        const request = vm.runInNewContext(`${code}\nrequestReleaseMetadata`, context);
        const instructions = vm.runInNewContext("installationInstructions", context);
        const selected = await request();
        const copied = instructions(selected);
        if (!copied.includes(`${release.archive_sha256}  ${release.archive_filename}`) ||
            !copied.includes("sha256sum -c -") ||
            !copied.includes(`cd ${release.archive_root}`) ||
            !copied.includes(`--sha256 ${release.wheel_sha256}`)) {
          throw new Error("instructions do not identify the approved artifact");
        }
        delete release.archive_sha256;
        try { await request(); throw new Error("missing identity was accepted"); }
        catch (error) {
          if (error.message === "missing identity was accepted") throw error;
        }
        """
    )


def test_release_management_shows_storage_failure_and_explicit_active_version():
    run_dashboard_harness(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("async function requestRegisteredReleases()"),
          source.indexOf("function openDeploymentDeleteDialog("),
        );
        const node = (tag, text = "") => ({
          tag, textContent: text, children: [], disabled: false,
          append(...children) { this.children.push(...children); },
          replaceChildren(...children) { this.children = children; },
          addEventListener() {},
        });
        const state = {
          releases: [], storage_status: "Release staging: incoming directory is unavailable.",
        };
        const context = {
          fetch: async () => ({ ok: true, json: async () => state }),
          document: { createElement: (tag) => node(tag) }, element: node,
          releaseList: node("list"), releaseActiveStatus: node("status"),
          releaseManagementStatus: node("status"),
          releaseRegisterName: { value: "skybeat-agent-1.0.5" },
          releaseRegisterSubmit: { disabled: false },
          requestDashboardMutation: async () => { throw new Error("staging unavailable"); },
          markDashboardFresh() {}, markDashboardStale() {},
        };
        const refresh = vm.runInNewContext(`${code}\nrefreshRegisteredReleases`, context);
        const register = vm.runInNewContext("registerRelease", context);
        await refresh();
        if (context.releaseActiveStatus.textContent !==
            "Active installation version: Not available" ||
            !context.releaseManagementStatus.textContent.includes("incoming directory")) {
          throw new Error("missing staging was hidden");
        }
        await register({ preventDefault() {} });
        if (!context.releaseManagementStatus.textContent.includes("incoming directory")) {
          throw new Error("registration failure hid the staging diagnosis");
        }
        state.storage_status = "Release store and staging directory: available.";
        state.releases = [{ version: "1.0.5", archive_sha256: "a".repeat(64),
          status: "VERIFIED", active: false, available: true }];
        await refresh();
        if (context.releaseActiveStatus.textContent !==
            "Active installation version: Not available") {
          throw new Error("inactive registration was shown as active");
        }
        state.releases[0].active = true;
        state.releases[0].status = "APPROVED";
        await refresh();
        if (context.releaseActiveStatus.textContent !== "Active installation version: v1.0.5") {
          throw new Error("active version was not shown");
        }
        """
    )
