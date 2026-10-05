"""Add Device preparation and one-time token handoff in the existing dashboard."""

import shutil
import subprocess
import textwrap
from pathlib import Path


def dashboard_script() -> str:
    return (Path(__file__).resolve().parents[1] / "app/static/dashboard.js").read_text(
        encoding="utf-8"
    )


def run_node(harness: str) -> None:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(  # noqa: S603 - locally discovered Node runs a fixed test harness
        [node, "--input-type=module", "--eval", textwrap.dedent(harness)],
        check=False,
        input=dashboard_script(),
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_prepare_device_creates_once_and_retries_only_the_token_handoff():
    run_node(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("async function submitEnrollment()"),
          source.indexOf("async function requestReleaseMetadata()"),
        );
        const projectId = "e3e70682-c209-4cac-a29f-6fbed82c07cd";
        const token = `sbe1.${projectId}.test-secret`;
        let posts = 0;
        let downloads = 0;
        const redirects = [];
        const field = (value = "") => ({ value, disabled: false });
        const context = {
          enrollmentSubmissionInFlight: false,
          enrollmentPreparedWithoutToken: false,
          enrollmentCredential: null,
          enrollmentId: null,
          enrollName: field(" GPU node "),
          enrollProject: field(projectId),
          enrollDescription: field("  Packing line GPU  "),
          enrollmentStatus: { textContent: "" },
          enrollSubmit: { disabled: false, textContent: "Prepare Device" },
          deviceEnrollClose: { disabled: false },
          enrollCancel: { disabled: false },
          newProjectFromEnroll: { disabled: false },
          requestDashboardMutation: async (path, method, payload) => {
            posts += 1;
            if (path !== "/api/v1/agent-enrollments" || method !== "POST") {
              throw new Error("wrong enrollment endpoint");
            }
            if (payload.name !== "GPU node" || payload.project_id !== projectId ||
                payload.description !== "Packing line GPU" ||
                "gpu_monitoring_enabled" in payload || "expected_gpu_min_count" in payload) {
              throw new Error("unexpected preparation payload");
            }
            return { token, enrollment: { enrollment_id: projectId } };
          },
          downloadEnrollmentToken: () => {
            downloads += 1;
            if (downloads === 1) throw new Error("download blocked");
          },
          window: { location: { assign(path) { redirects.push(path); } } },
        };
        const submit = vm.runInNewContext(`${code}\nsubmitEnrollment`, context);
        await submit();
        if (posts !== 1 || downloads !== 1 || redirects.length !== 0) {
          throw new Error("failed handoff created an incorrect preparation or redirect");
        }
        if (!context.enrollSubmit.textContent.includes("Save token file") ||
            context.enrollSubmit.disabled || context.enrollCancel.disabled !== true ||
            !context.enrollmentStatus.textContent.includes("Device prepared")) {
          throw new Error("failed handoff did not preserve a safe retry state");
        }
        await submit();
        if (posts !== 1 || downloads !== 2 ||
            redirects.join() !== "/dashboard/deployments") {
          throw new Error("retry created a second intent or failed to redirect");
        }
        """
    )


def test_prepare_device_rejects_duplicate_submit_and_keeps_api_errors_inline():
    run_node(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("async function submitEnrollment()"),
          source.indexOf("async function requestReleaseMetadata()"),
        );
        const field = (value = "") => ({ value, disabled: false });
        let posts = 0;
        let resolvePost;
        const redirects = [];
        const context = {
          enrollmentSubmissionInFlight: false,
          enrollmentPreparedWithoutToken: false,
          enrollmentCredential: null,
          enrollmentId: null,
          enrollName: field("GPU node"),
          enrollProject: field("e3e70682-c209-4cac-a29f-6fbed82c07cd"),
          enrollDescription: field(""),
          enrollmentStatus: { textContent: "" },
          enrollSubmit: { disabled: false, textContent: "Prepare Device" },
          deviceEnrollClose: { disabled: false },
          enrollCancel: { disabled: false },
          newProjectFromEnroll: { disabled: false },
          requestDashboardMutation: () => {
            posts += 1;
            return new Promise((resolve, reject) => { resolvePost = { resolve, reject }; });
          },
          downloadEnrollmentToken: () => { throw new Error("unexpected download"); },
          window: { location: { assign(path) { redirects.push(path); } } },
        };
        const submit = vm.runInNewContext(`${code}\nsubmitEnrollment`, context);
        const first = submit();
        await submit();
        if (posts !== 1 || context.enrollSubmit.textContent !== "Preparing...") {
          throw new Error("duplicate submission was not blocked");
        }
        resolvePost.reject(new Error("API unavailable"));
        await first;
        if (redirects.length || context.enrollSubmit.disabled ||
            context.enrollName.value !== "GPU node" ||
            !context.enrollmentStatus.textContent.includes("could not be prepared")) {
          throw new Error("API failure did not retain the editable draft");
        }
        """
    )


def test_token_file_uses_existing_name_and_revokes_blob_url_even_on_failure():
    run_node(
        """
        import fs from "node:fs";
        import vm from "node:vm";
        const source = fs.readFileSync(0, "utf8");
        const code = source.slice(
          source.indexOf("function downloadEnrollmentToken()"),
          source.indexOf("function openMoveDialog()"),
        );
        const enrollmentId = "e3e70682-c209-4cac-a29f-6fbed82c07cd";
        const token = `sbe1.${enrollmentId}.test-secret`;
        const saved = [];
        const revoked = [];
        let block = false;
        const context = {
          enrollmentCredential: token,
          enrollmentId,
          Blob: class { constructor(parts, options) { saved.push({ parts, options }); } },
          URL: {
            createObjectURL() { return "blob:temporary"; },
            revokeObjectURL(url) { revoked.push(url); },
          },
          document: { createElement() { return {
            click() {
              if (block) throw new Error("download blocked");
              saved.push({ name: this.download, href: this.href });
            },
          }; } },
        };
        const download = vm.runInNewContext(`${code}\ndownloadEnrollmentToken`, context);
        download();
        if (saved[0].parts[0] !== token || saved[0].options.type !== "text/plain" ||
            saved[1].name !== `skybeat-enrollment-${enrollmentId}.token` ||
            saved[1].href !== "blob:temporary" || revoked.length !== 1) {
          throw new Error("token file handoff changed its format or left a blob URL");
        }
        block = true;
        try { download(); throw new Error("blocked click unexpectedly succeeded"); }
        catch (error) {
          if (error.message !== "download blocked" || revoked.length !== 2) throw error;
        }
        """
    )
