# Stage 08A Design System Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a coherent, tokenized SkyBeat dashboard visual foundation while preserving every existing dashboard behavior and page structure.

**Architecture:** Keep the one-template/one-stylesheet/one-DOM-safe-controller architecture. Define layered primitive, semantic, and component `--sb-*` variables at the top of `dashboard.css`; migrate only existing shared CSS selectors to consume the layer; preserve the existing Jinja markup, routes, client behavior, and endpoint contracts. Use source-level regression tests to prove the foundation and existing behavioral safety guards coexist.

**Tech Stack:** FastAPI, Jinja2, vanilla DOM JavaScript, local CSS/SVG, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-24-stage08a-design-system-foundation-design.md`

## Global Constraints

- Preserve all existing routes, endpoint contracts, Jinja identifiers/sections, API payload semantics, authorization, polling cadence, filters, opaque keyset pagination, drawer/dialog flows, and canonical server-owned health logic.
- Do not modify Python application code, database schema/migrations, server/deployment/Caddy configuration, or API documentation.
- Do not introduce a frontend framework, component library, remote font, external icon library, chart library, WebSocket, SSE, or new dependency.
- Keep dynamic DOM rendering safe: no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, raw JSON rendering, browser credential storage, or new client-derived health states.
- Keep existing Jinja DOM structure, IDs, names, route links, labels, and event wiring unchanged. Do not undertake Stage 08B navigation, page, information-architecture, widget, filter-layout, drawer-content, or responsive-layout redesign.
- Use the layer order `primitive -> semantic -> component`; only primitive tokens contain literal design values, semantic tokens communicate purpose, and component tokens/rules consume semantic tokens.
- All operational presentation keeps canonical visible text. Green means healthy/success, amber warning/degraded, red critical/error/offline, blue informational/active-selection, and gray neutral/unknown/unavailable; no color alone communicates a state.
- Use existing Jinja markup and CSS selectors whenever possible. A semantic class may be added only when an existing selector cannot safely represent a shared primitive; adding it must not change hierarchy or behavior.
- Do not commit unless the user explicitly requests a commit.
- Keep Stage 07 recorded as `IMPLEMENTED / AWAITING BROWSER ACCEPTANCE`; Stage 08A implementation does not accept Stage 07 or begin Stage 08B.

## Review Focus

- **Canonical status labels:** `ONLINE`, `OFFLINE`, `OK`, `UNKNOWN`, and `AWAITING_FIRST_HEARTBEAT` must retain their exact visible text while receiving a dot and semantic tint; test in Task 2.
- **Unsafe DOM regression:** style work must not prompt a JavaScript rewrite that adds unsafe DOM APIs or local sensitive storage; test in Task 3.
- **High-density table regression:** table tokens must preserve sticky headers, horizontal overflow, and existing rows/filters rather than replace table structure; test in Task 2.
- **Keyboard-only operation:** shared `:focus-visible` styling must remain present for links and all native controls, independent of hover; test in Task 1.
- **Pending-browser honesty:** browser-rendered contrast/interaction cannot be claimed from source tests; record it as pending in the Stage 08A status update in Task 3.

---

## File structure

- Modify: `server/app/static/dashboard.css` — canonical CSS design tokens, reusable visual primitives, and migration of existing global/common selectors.
- Modify: `server/app/static/dashboard.js` — only replace static history palette literals with reads of CSS custom properties if required to make SVG history series consume tokens; no other behavioral change.
- Modify: `server/tests/test_dashboard_page.py` — source-level design-system and behavior-preservation regression tests.
- Modify: `docs/IMPLEMENTATION_STATUS.md` — factual Stage 08A completion checkpoint after all verification passes; retain the pending Stage 07 browser acceptance explicitly.

## Task 1: Lock the public design-system contract in tests

**Files:**
- Modify: `server/tests/test_dashboard_page.py`
- Read: `server/app/static/dashboard.css`
- Read: `server/app/static/dashboard.js`

**Interfaces:**
- Consumes: `dashboard_styles() -> str`, `dashboard_script() -> str`, and `dashboard_template() -> str` test helpers already defined in `test_dashboard_page.py`.
- Produces: source-level acceptance tests for the CSS public token names and non-behavioral dashboard constraints that Tasks 2 and 3 satisfy.

- [ ] **Step 1: Add failing foundation-contract tests to `server/tests/test_dashboard_page.py`**

  Add these tests after `test_dashboard_visual_system_preserves_accessibility_and_responsive_behavior`:

  ```python
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
      assert "content: \"\"" in styles
      assert ".status-online" in styles
      assert ".status-unknown" in styles
      assert "--sb-focus-ring" in styles
      assert ":focus-visible" in styles
      assert "position: sticky" in styles
      assert "overflow-x: auto" in styles
      assert "status-${displayValue(value).toLowerCase().replaceAll(\"_\", \"-\")}" in script
  ```

- [ ] **Step 2: Run the new tests to verify they fail before the stylesheet migration**

  Run:

  ```powershell
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server pytest server/tests/test_dashboard_page.py -q
  ```

  Expected: FAIL because the `--sb-*` token contract and `.status-pill::before` rule do not exist yet. Existing dashboard assertions must remain otherwise intact.

- [ ] **Step 3: Do not edit application code in this task**

  Keep the change test-only. Do not weaken existing assertions for routes, safe DOM, polling, drawer behavior, or management flows.

- [ ] **Step 4: Leave the test in its expected failing state for Task 2**

  Do not mark Stage 08A verified until Task 2 adds the required implementation and the focused suite passes.

## Task 2: Implement token layers and common CSS foundations

**Files:**
- Modify: `server/app/static/dashboard.css`
- Modify: `server/app/static/dashboard.js` only if needed for tokenized history-series colors
- Test: `server/tests/test_dashboard_page.py`

**Interfaces:**
- Consumes: the `--sb-*` contract asserted by Task 1 and the existing class/ID selectors in `dashboard.html` and dynamic elements created by `dashboard.js`.
- Produces: a CSS-only reusable design-system foundation that later page stages can consume without changing page composition.

- [ ] **Step 1: Define primitive, semantic, and component token blocks at the top of `dashboard.css`**

  Replace the current generic `:root` tokens with a token block in this ordering and with concrete accessible values:

  ```css
  :root {
    /* Primitive: raw palette, geometry, type and effects. */
    --sb-color-slate-25: #f8fafc;
    --sb-color-slate-50: #f3f6fa;
    --sb-color-slate-100: #e8eef5;
    --sb-color-slate-200: #d7e0ea;
    --sb-color-slate-300: #bcc9d8;
    --sb-color-slate-500: #64748b;
    --sb-color-slate-700: #334155;
    --sb-color-slate-900: #172033;
    --sb-color-navy-800: #18304f;
    --sb-color-navy-900: #10233f;
    --sb-color-blue-50: #eaf2ff;
    --sb-color-blue-100: #d8e8ff;
    --sb-color-blue-600: #1769d1;
    --sb-color-blue-700: #0f59b2;
    --sb-color-green-50: #e6f6f0;
    --sb-color-green-700: #087860;
    --sb-color-amber-50: #fff4df;
    --sb-color-amber-700: #8a4d00;
    --sb-color-red-50: #fdebea;
    --sb-color-red-700: #b42318;
    --sb-space-1: 0.25rem;
    --sb-space-2: 0.5rem;
    --sb-space-3: 0.75rem;
    --sb-space-4: 1rem;
    --sb-space-5: 1.25rem;
    --sb-space-6: 1.5rem;
    --sb-space-8: 2rem;
    --sb-radius-sm: 0.375rem;
    --sb-radius-md: 0.55rem;
    --sb-radius-lg: 0.7rem;
    --sb-shadow-sm: 0 0.15rem 0.6rem rgb(23 32 51 / 6%);
    --sb-shadow-md: 0 0.4rem 1.6rem rgb(23 32 51 / 8%);
    --sb-font-sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --sb-font-mono: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    --sb-font-size-xs: 0.72rem;
    --sb-font-size-sm: 0.82rem;
    --sb-font-size-md: 0.92rem;
    --sb-font-size-lg: 1.2rem;
    --sb-font-size-xl: clamp(1.55rem, 2.2vw, 2rem);
    --sb-line-height-tight: 1.2;
    --sb-line-height-normal: 1.5;
    --sb-focus-ring-width: 0.1875rem;
    --sb-control-height: 2.3rem;

    /* Semantic: purpose-derived values only. */
    --sb-bg-app: var(--sb-color-slate-50);
    --sb-bg-surface: #fff;
    --sb-bg-surface-secondary: var(--sb-color-slate-25);
    --sb-bg-sidebar: var(--sb-color-navy-900);
    --sb-bg-hover: var(--sb-color-blue-50);
    --sb-bg-selected: var(--sb-color-blue-100);
    --sb-text-primary: var(--sb-color-slate-900);
    --sb-text-secondary: var(--sb-color-slate-700);
    --sb-text-muted: var(--sb-color-slate-500);
    --sb-text-inverse: #fff;
    --sb-border: var(--sb-color-slate-200);
    --sb-border-strong: var(--sb-color-slate-300);
    --sb-focus-ring: #69a8f5;
    --sb-primary: var(--sb-color-blue-600);
    --sb-primary-hover: var(--sb-color-blue-700);
    --sb-primary-soft: var(--sb-color-blue-50);
    --sb-success: var(--sb-color-green-700);
    --sb-success-soft: var(--sb-color-green-50);
    --sb-warning: var(--sb-color-amber-700);
    --sb-warning-soft: var(--sb-color-amber-50);
    --sb-danger: var(--sb-color-red-700);
    --sb-danger-soft: var(--sb-color-red-50);
    --sb-info: var(--sb-color-blue-700);
    --sb-info-soft: var(--sb-color-blue-50);
    --sb-neutral: var(--sb-color-slate-700);
    --sb-neutral-soft: var(--sb-color-slate-100);

    /* Component: aliases consumed by shared rules. */
    --sb-control-bg: var(--sb-bg-surface);
    --sb-control-border: var(--sb-border-strong);
    --sb-control-focus-ring: var(--sb-focus-ring);
    --sb-button-primary-bg: var(--sb-primary);
    --sb-button-primary-hover: var(--sb-primary-hover);
    --sb-table-header-bg: var(--sb-bg-surface-secondary);
    --sb-drawer-bg: var(--sb-bg-surface);
    --sb-status-ok-fg: var(--sb-success);
    --sb-status-ok-bg: var(--sb-success-soft);
    --sb-status-warning-fg: var(--sb-warning);
    --sb-status-warning-bg: var(--sb-warning-soft);
    --sb-status-danger-fg: var(--sb-danger);
    --sb-status-danger-bg: var(--sb-danger-soft);
    --sb-status-info-fg: var(--sb-info);
    --sb-status-info-bg: var(--sb-info-soft);
    --sb-status-neutral-fg: var(--sb-neutral);
    --sb-status-neutral-bg: var(--sb-neutral-soft);
    --sb-history-series-1: var(--sb-primary);
    --sb-history-series-2: #7a3ec8;
    --sb-history-series-3: #007f6d;
    --sb-history-series-4: #b54708;
  }
  ```

  Do not retain old generic `--bg`, `--surface`, `--navy`, `--text`, `--muted`, `--border`, `--accent`, `--success`, `--warning`, `--danger`, `--radius`, or `--shadow` aliases. Update consumers to `--sb-*` names instead.

- [ ] **Step 2: Add reusable primitive rules and migrate common selectors without changing markup**

  Place the shared rules immediately after CSS resets. Use existing selectors, plus additive reusable classes for future consumers, and map them into the following behavior:

  ```css
  body {
    background: var(--sb-bg-app);
    color: var(--sb-text-primary);
    font-family: var(--sb-font-sans);
    font-size: var(--sb-font-size-md);
    line-height: var(--sb-line-height-normal);
  }

  .sb-surface,
  .overview-card,
  #project-summary,
  .controls,
  .device-table-region,
  .detail-panel,
  .attention-section {
    background: var(--sb-bg-surface);
    border: 1px solid var(--sb-border);
    border-radius: var(--sb-radius-lg);
  }

  button,
  input,
  select {
    background: var(--sb-control-bg);
    border: 1px solid var(--sb-control-border);
    border-radius: var(--sb-radius-sm);
    color: var(--sb-text-primary);
    min-height: var(--sb-control-height);
  }

  button:focus-visible,
  input:focus-visible,
  select:focus-visible,
  a:focus-visible {
    outline: var(--sb-focus-ring-width) solid var(--sb-control-focus-ring);
    outline-offset: 0.125rem;
  }

  .sb-technical,
  code,
  .detail-panel dd,
  .history-summary dd {
    font-family: var(--sb-font-mono);
    font-variant-numeric: tabular-nums;
  }
  ```

  Then migrate existing sidebar, header, headings, text metadata, metric cards, project cards, controls, filter popovers, attention surfaces, table, detail panel, history cards, dialogs, and credential-warning selectors to semantic/component tokens and spacing/radius/shadow tokens. Retain existing grid definitions, media query breakpoints, table `min-width`, drawer fixed positioning, and dialog behavior.

- [ ] **Step 3: Implement the compact status dot and canonical state mapping in CSS only**

  Replace the current `.status-pill` styling with a shared dot-and-label presentation. Do not alter `statusPill()` or rename its generated classes.

  ```css
  .status-pill {
    align-items: center;
    background: var(--sb-status-neutral-bg);
    border-radius: 999px;
    color: var(--sb-status-neutral-fg);
    display: inline-flex;
    font-size: var(--sb-font-size-xs);
    font-weight: 700;
    gap: var(--sb-space-1);
    letter-spacing: 0.025em;
    padding: var(--sb-space-1) var(--sb-space-2);
    white-space: nowrap;
  }

  .status-pill::before {
    background: currentColor;
    border-radius: 50%;
    content: "";
    flex: 0 0 auto;
    height: 0.45rem;
    width: 0.45rem;
  }

  .status-online,
  .status-ok,
  .status-healthy,
  .status-resolved { background: var(--sb-status-ok-bg); color: var(--sb-status-ok-fg); }
  .status-suspect,
  .status-warning,
  .status-degraded { background: var(--sb-status-warning-bg); color: var(--sb-status-warning-fg); }
  .status-offline,
  .status-critical,
  .status-driver-error,
  .status-gpu-missing,
  .status-nvidia-smi-failed { background: var(--sb-status-danger-bg); color: var(--sb-status-danger-fg); }
  .status-awaiting-first-heartbeat,
  .status-active { background: var(--sb-status-info-bg); color: var(--sb-status-info-fg); }
  .status-unknown,
  .status-not-monitored { background: var(--sb-status-neutral-bg); color: var(--sb-status-neutral-fg); }
  ```

  The generated text node is the visible canonical label. The pseudo-element is decorative and must not change accessible text.

- [ ] **Step 4: Tokenize SVG history colors without changing chart behavior**

  In `dashboard.js`, replace the color-literal array with CSS variable names and resolve each value exactly at assignment time:

  ```javascript
  const HISTORY_COLOR_TOKENS = [
    "--sb-history-series-1",
    "--sb-history-series-2",
    "--sb-history-series-3",
    "--sb-history-series-4",
  ];

  function historyColor(index) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(HISTORY_COLOR_TOKENS[index % HISTORY_COLOR_TOKENS.length])
      .trim();
  }
  ```

  Replace both uses of `HISTORY_COLORS[index % HISTORY_COLORS.length]` with `historyColor(index)`. Retain the number/order of colors, SVG nodes, labels, legends, data calculations, and safe DOM APIs.

- [ ] **Step 5: Run the focused dashboard page tests and confirm the new tests pass**

  Run:

  ```powershell
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server pytest server/tests/test_dashboard_page.py -q
  ```

  Expected: PASS, including all existing route, safe-DOM, polling, filters, drawer/history, management-dialog, and accessibility-source tests.

## Task 3: Add final source guards, verify regressions, and checkpoint truthfully

**Files:**
- Modify: `server/tests/test_dashboard_page.py`
- Modify: `docs/IMPLEMENTATION_STATUS.md`
- Read: `server/app/static/dashboard.css`
- Read: `server/app/static/dashboard.js`

**Interfaces:**
- Consumes: the tokenized stylesheet and (only if changed) `HISTORY_COLOR_TOKENS`/`historyColor(index)` from Task 2.
- Produces: final source guards and a factual persistent Stage 08A implementation checkpoint.

- [ ] **Step 1: Add source tests that protect Stage 08A scope boundaries**

  Add these tests to `server/tests/test_dashboard_page.py`:

  ```python
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
          "device-status-table",
          "detail-panel",
          "project-dialog",
          "device-enroll-dialog",
      ):
          assert f'id="{identifier}"' in template or identifier == "device-status-table"
      assert 'href="/dashboard"' in template
      assert 'href="/dashboard/devices"' in template
      assert 'href="/dashboard/projects"' in template
  ```

  For `device-status-table`, keep the exception because JavaScript creates it dynamically; do not move it into Jinja merely to satisfy the test.

- [ ] **Step 2: Run the focused dashboard test file and inspect the changed files**

  Run:

  ```powershell
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server pytest server/tests/test_dashboard_page.py -q
  git diff --check
  git diff -- server/app/static/dashboard.css server/app/static/dashboard.js server/tests/test_dashboard_page.py
  ```

  Expected: tests pass; `git diff --check` has no whitespace errors; the diff is limited to CSS foundation, optional tokenized history colors, and tests.

- [ ] **Step 3: Run affected full verification**

  Run:

  ```powershell
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server pytest -q
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server ruff check app tests
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server ruff format --check app tests
  & 'D:\Dinesh\deviceHealth\.tmp\uv-tool\Scripts\uv.exe' --cache-dir 'D:\learning\skybeat\skybeat\.tmp\uv-cache' run --project server mypy
  ```

  Expected: the full server suite passes subject only to already-documented environment skips; Ruff, formatting, and strict mypy pass. No agent suite is required because no agent/shared-contract code changes.

- [ ] **Step 4: Perform browser-level verification only if a local browser/application environment is safely available**

  With development-only authentication bypass enabled only in the protected ignored local environment file, verify authenticated load, all existing route navigation, data render, filters, pagination, drawer/dialog workflows, polling, keyboard focus visibility, reduced motion, responsive behavior, and browser console errors. Do not change credentials, retained MySQL files, ACLs, migrations, or production infrastructure to make this possible.

  If the local browser/application environment is unavailable, record this as an environment limitation. Do not report browser acceptance as passed.

- [ ] **Step 5: Update `docs/IMPLEMENTATION_STATUS.md` only after successful executable verification**

  Add a concise Stage 08A checkpoint that records:

  ```markdown
  - Stage: 08A - Design System Foundation.
  - Status: IMPLEMENTED / AWAITING BROWSER ACCEPTANCE if browser checks remain unavailable; otherwise record the actual browser result.
  - Files changed: dashboard CSS, optional history-color token bridge, dashboard page tests, Stage 08A spec/plan, and this checkpoint.
  - Migrations: none; no backend/API/deployment behavior changed.
  - Tests executed: exact commands and actual pass/fail/skip counts.
  - Security implications: existing same-origin, DOM-safe rendering, auth/session, and server-owned health semantics retained.
  - Known limitations: only actual unverified browser/contrast/interaction conditions.
  - Next stage: STOP. Do not begin Stage 08B.
  ```

  Preserve the existing Stage 07 pending-browser acceptance language. Do not replace it with a Stage 08 claim.

- [ ] **Step 6: Do not commit without user authorization**

  Leave the worktree uncommitted unless the user explicitly asks for a commit. Report the exact modified files and verification evidence.

## Plan self-review

### Spec coverage

- Token layering, complete semantic token families, typography, spacing, surfaces, controls, buttons, tables, statuses, drawer/dialog foundations, technical values, focus/reduced-motion behavior, migration constraints, test strategy, acceptance criteria, risks, and the Stage 07/08B boundaries are covered by Tasks 1–3.
- The design explicitly forbids API/backend/configuration/migration work and page/navigation redesign; every task repeats those boundaries.
- Browser-only assertions are assigned to Task 3 and must be recorded truthfully if the environment is unavailable.

### Placeholder scan

The tasks use concrete file paths, selectors, CSS values, tests, commands, and expected outcomes. No implementation placeholder remains.

### Interface consistency

Task 1 defines token-test names consumed by Task 2. Task 2 defines `HISTORY_COLOR_TOKENS` and `historyColor(index)` only if the JavaScript history bridge is used; Task 3 asserts the same exact names. Existing `statusPill()` output class contract is retained unchanged.

### Review-focus coverage

- Canonical state labels and dot/tint coverage: Task 2 status CSS plus Task 1 test.
- Safe DOM and storage regression: Task 3 source test.
- Sticky/high-density table preservation: Task 1 source test and Task 2 migration constraint.
- Keyboard focus: Task 1 source test and Task 2 shared focus rule.
- Pending browser verification: Task 3 browser procedure and status checkpoint.
