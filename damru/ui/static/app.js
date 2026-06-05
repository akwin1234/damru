const pages = [
  { id: "dashboard", path: "/", label: "Dashboard", glyph: "H", title: "Dashboard", kicker: "Runtime" },
  { id: "setup", path: "/setup", label: "Setup", glyph: "S", title: "Setup", kicker: "First run" },
  { id: "workers", path: "/workers", label: "Workers", glyph: "W", title: "Workers", kicker: "Devices" },
  { id: "work", path: "/work", label: "Work Lab", glyph: "B", title: "Work Lab", kicker: "Browser" },
  { id: "settings", path: "/settings", label: "Settings", glyph: "C", title: "Settings", kicker: "Config" },
  { id: "logs", path: "/logs", label: "Logs", glyph: "L", title: "Logs", kicker: "Jobs" },
];

const pageByPath = Object.fromEntries(pages.map((page) => [page.path, page.id]));
pageByPath["/work-lab"] = "work";
pageByPath["/viewer"] = "work";
const pageById = Object.fromEntries(pages.map((page) => [page.id, page]));

const setupSteps = [
  { key: "check-env", label: "Check environment", detail: "Reads Docker, binderfs, APK, image, viewer, and WSL state.", action: "check-env", runLabel: "Check now", doneLabel: "Check again" },
  { key: "deps", label: "Install dependencies", detail: "Installs Linux packages such as Docker, ADB, curl, wget, jq, iptables, and module tooling.", action: "install-deps", runLabel: "Install deps", doneLabel: "Reinstall" },
  { key: "runtime", label: "Repair runtime", detail: "Applies safe Docker, binderfs, iptables, NAT, and WSL route repairs.", action: "fix-wsl", runLabel: "Repair", doneLabel: "Repair again" },
  { key: "apks", label: "Install APK bundle", detail: "Downloads and extracts the Chrome, WebView, TTS, RHVoice, eSpeak, and Magisk bundle.", action: "install-apks", runLabel: "Install APKs", doneLabel: "Reinstall" },
  { key: "image", label: "Install Redroid image", detail: "Loads or downloads the baked Damru Redroid Docker image.", action: "install-image", runLabel: "Install image", doneLabel: "Reload image" },
  { key: "viewer", label: "Install native viewer", detail: "Optional scrcpy support for users who want a separate native window.", action: "install-viewer", runLabel: "Install", doneLabel: "Reinstall" },
];

const confirmMeta = {
  "install-deps": { title: "Install Linux dependencies?", body: "Damru will install required packages for Docker, ADB, network tooling, and runtime checks on the configured host." },
  "fix-wsl": { title: "Repair runtime networking and binderfs?", body: "Damru will run safe Docker, binderfs, iptables, NAT, and WSL route repair commands. Existing Damru workers may reconnect." },
  "install-apks": { title: "Install APK bundle?", body: "Damru will download or extract the APK bundle and update the local APK path when needed." },
  "install-image": { title: "Install Redroid image?", body: "Damru will download or load the baked Docker image. This can take a while and uses several GB of disk." },
  "install-viewer": { title: "Install native viewer tools?", body: "Damru will install scrcpy for optional native windows. The browser viewer works without this." },
  "wsl-kernel-install": { title: "Install the Damru WSL kernel?", body: "This changes Windows .wslconfig. Use a dedicated WSL distro." },
  "stop-worker": { title: "Stop this worker?", body: "The selected Redroid container will stop. Any browser session running on it will end." },
  "resume-worker": { title: "Start this worker?", body: "Damru will start the existing stopped container without deleting its state." },
  "resume-workers": { title: "Start stopped workers?", body: "Damru will start existing stopped Damru containers. If none exist, it will start the configured worker count." },
  "delete-worker": { title: "Delete this worker?", body: "The selected Redroid container will be removed. Use Stop if you only want to pause it." },
  "restart-worker": { title: "Restart this worker?", body: "The selected Redroid container will restart. Current browser state on that worker will be lost." },
  "stop-workers": { title: "Stop all Damru workers?", body: "All Damru Redroid containers managed by this UI will be stopped. Other Docker resources are not touched." },
  "delete-workers": { title: "Delete all Damru workers?", body: "All Damru Redroid containers managed by this UI will be removed. This is not the same as Stop all." },
  "add-workers": { title: "Add workers?", body: "Damru will add the requested number of new Redroid workers using the next free worker indexes." },
  "restore-config": { title: "Restore latest config backup?", body: "Damru will replace the current config.py with the newest backup created by this UI." },
  "proof": { title: "Run stealth checker?", body: "Damru will visit proof targets and capture screenshots. This may take several minutes and uses the selected proxy if provided." },
  "quick-check": { title: "Run quick checker?", body: "Damru will run a fast local Android/Chrome sanity check, save JSON, and open a local checker page inside Chrome." },
  "proof-all": { title: "Run stealth checker on all workers?", body: "Damru will run the stealth checker sequentially on every running Damru worker and save one proof folder per worker." },
  "clear-captures": { title: "Clear gallery?", body: "Damru will delete screenshots, recordings, proof folders, and JSON reports from the local capture folder only." },
  "clear-logs": { title: "Clear finished logs?", body: "Damru will remove finished UI job records from this dashboard. Running jobs are kept." },
  "fix-internet": { title: "Fix internet?", body: "Damru will repair WSL routing, Docker NAT, and Android DNS for the selected worker." },
  "random-profile": { title: "Apply random stealth profile?", body: "Damru will pick a compatible Android profile, rotate Chrome from the APK bundle when available, apply system props, screen, locale, timezone, and Chrome settings, then stop Chrome for the next launch." },
};

const state = {
  page: "dashboard",
  health: null,
  workers: [],
  adb: [],
  jobs: [],
  captures: [],
  config: {},
  configBackups: [],
  selectedJob: null,
  selectedJobDetail: null,
  refreshedArtifacts: new Set(),
  showPassingChecks: false,
  activeButton: null,
  selectedSerial: localStorage.getItem("damru:selectedSerial") || "",
  viewer: { running: false, timer: null, serial: "", size: null, lastUrl: "", objectUrl: "", frameWidth: 0, frameHeight: 0, tapHoldUntil: 0, frameLoading: false, pendingFrame: false, pointer: null, markerTimer: null, textBuffer: "", textTimer: null },
  viewerBusy: false,
  poll: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));
}

function toast(message, type = "") {
  const node = document.createElement("div");
  node.className = `toast ${type}`.trim();
  node.textContent = message;
  $("toastStack").appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

function setButtonBusy(button, busy) {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.dataset.originalText || button.textContent;
    button.textContent = "Running...";
    button.disabled = true;
    button.classList.add("is-busy");
    state.activeButton = button;
    return;
  }
  button.textContent = button.dataset.originalText || button.textContent;
  button.disabled = false;
  button.classList.remove("is-busy");
  delete button.dataset.originalText;
  if (state.activeButton === button) state.activeButton = null;
}

function confirmAction(action, payload = {}) {
  let meta = confirmMeta[action];
  if (action === "fix-internet" && !payload.serial) {
    meta = { title: "Fix internet for all workers?", body: "Damru will repair WSL routing, Docker NAT, host DNS, and any reachable Android worker DNS." };
  }
  if (action === "random-profile" && payload.all) {
    meta = { title: "Apply random profiles to all workers?", body: "Damru will apply a different random Android profile to each running Damru worker, rotate Chrome from the APK bundle when available, then stop Chrome so the next launch uses it." };
  }
  if (!meta) return Promise.resolve(true);
  return new Promise((resolve) => {
    const modal = $("confirmModal");
    $("confirmTitle").textContent = meta.title;
    $("confirmBody").textContent = meta.body;
    $("confirmRunBtn").textContent = action === "wsl-kernel-install" ? "Install kernel" : "Run action";
    modal.classList.remove("hidden");
    const cleanup = (answer) => {
      modal.classList.add("hidden");
      $("confirmRunBtn").removeEventListener("click", onRun);
      $("confirmCancelBtn").removeEventListener("click", onCancel);
      modal.removeEventListener("click", onBackdrop);
      resolve(answer);
    };
    const onRun = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onBackdrop = (event) => { if (event.target === modal) cleanup(false); };
    $("confirmRunBtn").addEventListener("click", onRun);
    $("confirmCancelBtn").addEventListener("click", onCancel);
    modal.addEventListener("click", onBackdrop);
    $("confirmCancelBtn").focus();
  });
}

async function runAction(action, payload = {}, button = null) {
  if (!action || action === "none") return null;
  if (action === "workers") {
    showPage("workers");
    return null;
  }
  const confirmed = await confirmAction(action, payload);
  if (!confirmed) return null;
  setButtonBusy(button, true);
  try {
    const data = await api("/api/jobs/run", { method: "POST", body: JSON.stringify({ action, ...payload }) });
    toast(`${data.job.name} started`, "ok");
    state.selectedJob = data.job.id;
    state.selectedJobDetail = null;
    showJobNotice(data.job);
    showJobResult(data.job);
    refreshAll().catch(() => {});
    return data.job;
  } catch (error) {
    toast(error.message, "bad");
    throw error;
  } finally {
    setButtonBusy(button, false);
  }
}

function showJobNotice(job) {
  const box = $("activeJobNotice");
  box.classList.remove("hidden");
  box.innerHTML = `<div><strong>${escapeHtml(job.name)}</strong><span>${escapeHtml(job.status)}. You can keep working here while it runs.</span></div><button class="button secondary" type="button" data-job="${escapeHtml(job.id)}">View log</button>`;
}

function summarizeLog(log) {
  const lines = String(log || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !line.toLowerCase().includes("warning: in the working copy"));
  return lines.slice(0, 8).join("\n") || "No output.";
}

function showJobResult(job) {
  const panel = $("jobResultPanel");
  if (!job) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const done = ["success", "failed"].includes(job.status);
  const pill = job.status === "success" ? "ok" : job.status === "failed" ? "bad" : "warn";
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="result-head">
      <div><strong>${escapeHtml(job.name)}</strong><span>${escapeHtml(done ? `Finished with ${job.status}` : `${job.status}. Running in background`)}</span></div>
      <span class="status-pill ${pill}">${escapeHtml(job.status)}</span>
    </div>
    <pre class="result-output">${escapeHtml(summarizeLog(job.log))}</pre>
    <div class="button-row"><button class="button secondary" type="button" data-job="${escapeHtml(job.id)}">Open full log</button></div>`;
}

function updateActiveJobNotice() {
  if (!state.selectedJob) return;
  const job = state.jobs.find((item) => item.id === state.selectedJob);
  if (job) showJobNotice(job);
}

async function refreshSelectedJobResult() {
  if (!state.selectedJob) return;
  const basic = state.jobs.find((item) => item.id === state.selectedJob);
  if (!basic) return;
  if (!["success", "failed"].includes(basic.status)) {
    showJobResult({ ...basic, log: "" });
    return;
  }
  if (state.selectedJobDetail?.id === basic.id && state.selectedJobDetail?.status === basic.status) {
    showJobResult(state.selectedJobDetail);
    return;
  }
  const detail = await api(`/api/jobs/${basic.id}`);
  state.selectedJobDetail = detail;
  showJobResult(detail);
  if (detail.status === "success" && detail.artifact?.startsWith("/captures/") && !state.refreshedArtifacts.has(detail.artifact)) {
    state.refreshedArtifacts.add(detail.artifact);
    refreshCaptures().catch(() => {});
  }
}

function buildNav() {
  $("navList").innerHTML = pages.map((page) => `
    <button class="nav-item" type="button" data-page="${page.id}" data-path="${page.path}">
      <span class="nav-glyph" aria-hidden="true">${page.glyph}</span>
      <span>${page.label}</span>
    </button>
  `).join("");
}

function pageFromPath() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  return pageByPath[path] || "dashboard";
}

function showPage(id, push = true) {
  state.page = id;
  $("logDrawer")?.classList.add("hidden");
  const pageMeta = pageById[id] || pageById.dashboard;
  if (push && window.location.pathname !== pageMeta.path) {
    history.pushState({ page: id }, "", pageMeta.path);
  }
  pages.forEach((page) => {
    const active = page.id === id;
    $(`page-${page.id}`).classList.toggle("active", active);
    document.querySelector(`[data-page="${page.id}"]`)?.classList.toggle("active", active);
    if (active) {
      $("pageTitle").textContent = page.title;
      $("pageKicker").textContent = page.kicker;
    }
  });
  if (id === "work") refreshCaptures().catch(() => {});
  if (id === "logs") renderJobs();
}

function statusClass(ok) { return ok ? "ok" : "bad"; }

function renderHealth() {
  const h = state.health;
  if (!h) return;
  const checks = h.checks || [];
  const passed = checks.filter((c) => c.ok).length;
  const total = checks.length || 1;
  const pct = Math.round((passed / total) * 100);
  const statusText = h.status === "ready" ? "Ready" : h.status === "unsupported" ? "Unsupported" : "Needs setup";

  $("healthTitle").textContent = statusText === "Ready" ? "Damru is ready" : statusText === "Unsupported" ? "Unsupported host" : "Setup needed";
  $("healthCopy").textContent = statusText === "Ready" ? "Core runtime checks passed." : "Run the recommended setup steps below. Failed checks explain what to do next.";
  $("healthPill").textContent = statusText;
  $("healthPill").className = `status-pill ${h.status === "ready" ? "ok" : h.status === "unsupported" ? "bad" : "warn"}`;
  $("healthBar").style.width = `${pct}%`;

  const failed = checks.filter((c) => !c.ok && c.key !== "viewer");
  const optional = checks.filter((c) => !c.ok && c.key === "viewer");
  const visibleChecks = state.showPassingChecks ? checks : [...failed, ...optional];
  if (!visibleChecks.length) {
    $("healthChecks").innerHTML = `<div class="checks-summary">
      <div><strong>All required checks passed</strong><span>${passed} of ${total} checks are OK. Passing details are hidden to keep this page calm.</span></div>
      <button class="button secondary" type="button" id="toggleHealthChecks">Show details</button>
    </div>`;
  } else {
    $("healthChecks").innerHTML = visibleChecks.map((c) => `
      <div class="check-item ${statusClass(c.ok)}">
        <strong>${escapeHtml(c.label)}</strong>
        <span>${escapeHtml(c.ok ? c.detail || "OK" : c.detail || "Needs attention")}</span>
        ${c.repair ? `<button class="button secondary check-action" type="button" data-action="${escapeHtml(c.repair)}">Fix</button>` : ""}
      </div>
    `).join("") + `<div class="checks-summary">
      <div><strong>${state.showPassingChecks ? "Showing all checks" : "Only issues are shown"}</strong><span>${failed.length ? `${failed.length} required issue(s) need attention.` : "No required issues found."}</span></div>
      <button class="button secondary" type="button" id="toggleHealthChecks">${state.showPassingChecks ? "Hide passing" : "Show all"}</button>
    </div>`;
  }

  $("criticalNotice").classList.toggle("hidden", failed.length === 0);
  $("criticalNotice").innerHTML = failed.length ? `<strong>${failed.length} setup issue${failed.length === 1 ? "" : "s"}:</strong> ${failed.map((c) => escapeHtml(c.label)).join(", ")}` : "";

  $("metricWorkers").textContent = h.workers?.running ?? 0;
  $("metricWorkersText").textContent = `${h.workers?.booted ?? 0} booted of ${h.workers?.count ?? 0} containers`;
  $("metricAdb").textContent = h.workers?.adb_devices?.length ?? 0;
  $("metricJobs").textContent = h.jobs?.length ?? 0;
  $("nextActionBtn").textContent = h.next_action?.label || "Refresh";
  $("nextActionBtn").dataset.action = h.next_action?.action || "none";

  renderHostSummary(h.env || {}, h.config || {});
  renderRecentJobs(h.jobs || []);
  renderSetup();
  renderSettings(state.config && Object.keys(state.config).length ? state.config : (h.config || {}), state.configBackups || []);
}

function renderHostSummary(env, config) {
  const rows = [
    ["Host", env.is_windows ? "Windows + WSL" : env.is_wsl_linux ? "WSL Linux" : env.is_native_linux ? "Native Linux" : env.platform],
    ["Kernel", env.kernel || "Unknown"],
    ["Python", env.python],
    ["Damru", env.damru_version],
    ["WSL distro", env.wsl_distro || "Not used"],
    ["Mode", config.MODE || "auto"],
    ["Workers", config.NUM_DEVICES || "1"],
    ["Image", config.REDROID_IMAGE || "damru-redroid:latest"],
  ];
  $("hostSummary").innerHTML = rows.map(([label, value]) => `<div class="summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("setupEnv").innerHTML = rows.slice(0, 5).map(([label, value]) => `<div class="summary-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  $("wslKernelPanel").classList.toggle("hidden", !env.is_windows);
}

function renderSetup() {
  const checks = state.health?.checks || [];
  const byKey = Object.fromEntries(checks.map((c) => [c.key, c]));
  const stepStatus = (step) => {
    if (step.action === "check-env") return checks.length ? "done" : "pending";
    if (step.action === "install-deps") return ["adb", "docker", "curl", "wget", "jq"].every((k) => byKey[k]?.ok) ? "done" : "failed";
    if (step.action === "fix-wsl") return ["docker-daemon", "binderfs"].every((k) => byKey[k]?.ok) ? "done" : "failed";
    if (step.action === "install-apks") return byKey.apks?.ok ? "done" : "failed";
    if (step.action === "install-image") return byKey.image?.ok ? "done" : "failed";
    if (step.action === "install-viewer") return byKey.viewer?.ok ? "done" : "failed";
    return "pending";
  };
  $("setupSteps").innerHTML = setupSteps.map((step, i) => {
    const st = stepStatus(step);
    return `<div class="setup-step ${st}">
      <div class="step-index">${i + 1}</div>
      <div><h3>${escapeHtml(step.label)}</h3><p>${escapeHtml(step.detail)}</p></div>
      <button class="button ${st === "done" ? "secondary" : "primary"}" type="button" data-action="${step.action}">${st === "done" ? step.doneLabel : step.runLabel}</button>
    </div>`;
  }).join("");
}

function renderRecentJobs(jobs) {
  $("recentJobs").innerHTML = jobs.length ? jobs.map(jobCard).join("") : `<div class="empty-state"><h3>No jobs yet</h3><p>Run a setup check or capture action to see progress here.</p></div>`;
}

function jobCard(job) {
  return `<div class="job-item">
    <div><strong>${escapeHtml(job.name)}</strong><div class="muted mono">${escapeHtml(job.status)} ${job.returncode === null ? "" : `(${job.returncode})`}</div></div>
    <button class="button secondary" type="button" data-job="${job.id}">Open</button>
  </div>`;
}

function renderWorkers() {
  const q = ($("workerSearch")?.value || "").toLowerCase();
  const workers = state.workers.filter((w) => JSON.stringify(w).toLowerCase().includes(q));
  if ($("addWorkerBtn")) {
    $("addWorkerBtn").disabled = false;
    $("addWorkerBtn").title = "Add the requested number of Damru workers";
  }
  $("workersEmpty").classList.toggle("hidden", workers.length !== 0);
  $("workersTable").innerHTML = workers.map((w) => {
    const running = w.state === "running";
    const bootClass = w.boot === "booted" ? "ok" : w.boot === "stopped" ? "bad" : "warn";
    const serial = workerSerial(w);
    const index = workerIndex(w);
    const sessionButtons = running
      ? `<button class="button secondary" type="button" data-select-serial="${escapeHtml(serial)}" data-page="work" data-scroll-target="viewerPanel">Viewer</button><button class="button secondary" type="button" data-select-serial="${escapeHtml(serial)}" data-page="work" data-scroll-target="browserTaskPanel">Work</button><button class="button secondary" type="button" data-worker-action="fix-internet" data-serial="${escapeHtml(serial)}" data-index="${index}">Fix internet</button><button class="button secondary" type="button" data-worker-action="random-profile" data-serial="${escapeHtml(serial)}" data-index="${index}">Random profile</button><button class="button secondary" type="button" data-select-serial="${escapeHtml(serial)}" data-page="work" data-scroll-target="browserTaskPanel" data-autoproof="1">Stealth checker</button>`
      : `<button class="button secondary" type="button" data-worker-action="resume" data-index="${index}">Start</button>`;
    const lifecycleButtons = running
      ? `<button class="button secondary" type="button" data-worker-action="restart" data-index="${index}">Restart</button><button class="button danger subtle" type="button" data-worker-action="stop" data-index="${index}">Stop</button><button class="button danger subtle" type="button" data-worker-action="delete" data-index="${index}">Delete</button>`
      : `<button class="button secondary" type="button" data-worker-action="restart" data-index="${index}">Restart</button><button class="button danger subtle" type="button" data-worker-action="delete" data-index="${index}">Delete</button>`;
    return `
      <tr>
        <td><strong>${escapeHtml(w.name || w.id || "unknown")}</strong><div class="muted mono">${escapeHtml(w.id || "")}</div></td>
        <td><span class="status-pill ${running ? "ok" : "warn"}">${escapeHtml(w.state || "unknown")}</span><div class="muted">${escapeHtml(w.status || "")}</div></td>
        <td><span class="status-pill ${bootClass}">${escapeHtml(w.boot || "unknown")}</span></td>
        <td>${escapeHtml(w.image || "")}</td>
        <td class="mono">${escapeHtml(w.ports || "")}</td>
        <td><div class="button-row">${sessionButtons}${lifecycleButtons}</div></td>
      </tr>`;
  }).join("");
  renderSerialOptions();
}

function workerIndex(worker) {
  const match = String(worker.name || "").match(/(\d+)$/);
  return match ? Number(match[1]) : 0;
}

function workerSerial(worker) {
  const index = workerIndex(worker);
  const base = Number(state.health?.config?.REDROID_BASE_PORT || state.health?.config?.BASE_ADB_PORT || 5600);
  const host = `127.0.0.1:${base + index}`;
  return state.health?.env?.is_windows ? `wsl:${host}` : host;
}

function setSelectedSerial(serial) {
  if (!serial) return;
  state.selectedSerial = serial;
  localStorage.setItem("damru:selectedSerial", serial);
  ["taskSerial", "viewerSerial"].forEach((id) => {
    const select = $(id);
    if (!select) return;
    const exists = Array.from(select.options).some((option) => option.value === serial);
    if (exists) select.value = serial;
  });
}

function switchViewerSerialFast(serial) {
  if (!serial || !state.viewer.running || state.viewer.serial === serial) return;
  state.viewer.serial = serial;
  state.viewer.size = null;
  state.viewer.frameWidth = 0;
  state.viewer.frameHeight = 0;
  state.viewer.pendingFrame = false;
  viewerStatus(`Switching: ${serial}`);
  refreshViewerFrame();
  api(`/api/viewer/size?serial=${encodeURIComponent(serial)}`).then((size) => {
    if (state.viewer.serial === serial) state.viewer.size = size.width && size.height ? size : null;
  }).catch(() => {});
}

function renderSerialOptions() {
  const devices = state.adb || [];
  const previous = state.selectedSerial || $("taskSerial")?.value || $("viewerSerial")?.value || "";
  const options = devices.length ? devices.map((d) => `<option value="${escapeHtml(d.serial)}">${escapeHtml(d.serial)} (${escapeHtml(d.state)})</option>`).join("") : `<option value="">No online ADB device</option>`;
  $("taskSerial").innerHTML = options;
  $("viewerSerial").innerHTML = options;
  const nextSerial = devices.some((device) => device.serial === previous) ? previous : (devices[0]?.serial || "");
  if (nextSerial) setSelectedSerial(nextSerial);
  const disabled = devices.length === 0;
  $("runProofBtn").disabled = disabled;
  $("runProofAllBtn").disabled = disabled;
  $("openUrlBtn").disabled = disabled;
  $("fixInternetBtn").disabled = disabled;
  $("randomProfileBtn").disabled = disabled;
  $("randomProfileAllBtn").disabled = disabled;
  $("quickCheckBtn").disabled = disabled;
  $("screenshotBtn").disabled = disabled;
  $("launchViewerBtn").disabled = disabled;
  $("viewerScreenshotBtn").disabled = disabled;
  $("viewerRecordBtn").disabled = disabled;
  $("viewerSendTextBtn").disabled = disabled;
  $("viewerTextInput").disabled = disabled;
}

function viewerStatus(text) {
  $("viewerStatus").textContent = text;
}

function scheduleViewerFrame(delay = 260) {
  if (!state.viewer.running) return;
  if (state.viewer.timer) clearTimeout(state.viewer.timer);
  state.viewer.timer = setTimeout(refreshViewerFrame, delay);
}

function stopViewer() {
  state.viewer.running = false;
  if (state.viewer.timer) clearTimeout(state.viewer.timer);
  state.viewer.timer = null;
  state.viewer.frameLoading = false;
  state.viewer.pendingFrame = false;
  state.viewer.pointer = null;
  state.viewer.textBuffer = "";
  if (state.viewer.textTimer) clearTimeout(state.viewer.textTimer);
  state.viewer.textTimer = null;
  hideViewerMarker();
  const img = $("viewerImage");
  if (img) {
    img.removeAttribute("src");
    img.classList.add("hidden");
  }
  if (state.viewer.objectUrl) URL.revokeObjectURL(state.viewer.objectUrl);
  state.viewer.objectUrl = "";
  $("viewerPlaceholder")?.classList.remove("hidden");
  $("launchViewerBtn").textContent = "Open viewer";
  viewerStatus("Stopped");
}

async function refreshViewerFrame() {
  if (!state.viewer.running || !state.viewer.serial) return;
  if (state.viewer.frameLoading) {
    state.viewer.pendingFrame = true;
    return;
  }
  state.viewer.frameLoading = true;
  const img = $("viewerImage");
  const serial = state.viewer.serial;
  const url = `/api/viewer/frame?serial=${encodeURIComponent(state.viewer.serial)}&t=${Date.now()}`;
  let nextObjectUrl = "";
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Frame failed: ${response.status}`);
    }
    const blob = await response.blob();
    nextObjectUrl = URL.createObjectURL(blob);
    const loaded = await new Promise((resolve, reject) => {
      const probe = new Image();
      probe.onload = () => resolve({ width: probe.naturalWidth, height: probe.naturalHeight });
      probe.onerror = reject;
      probe.src = nextObjectUrl;
    });
    if (!state.viewer.running || state.viewer.serial !== serial) {
      URL.revokeObjectURL(nextObjectUrl);
      state.viewer.frameLoading = false;
      if (state.viewer.running) scheduleViewerFrame(80);
      return;
    }
    if (state.viewer.objectUrl) URL.revokeObjectURL(state.viewer.objectUrl);
    state.viewer.objectUrl = nextObjectUrl;
    nextObjectUrl = "";
    img.src = state.viewer.objectUrl;
    img.classList.remove("hidden");
    $("viewerPlaceholder").classList.add("hidden");
    if (loaded.width && loaded.height) {
      state.viewer.frameWidth = loaded.width;
      state.viewer.frameHeight = loaded.height;
    }
    state.viewer.lastUrl = url;
    if (Date.now() > state.viewer.tapHoldUntil) viewerStatus(`Live: ${state.viewer.serial}`);
  } catch (error) {
    if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl);
    viewerStatus(error.message || "Frame failed. Device may be booting.");
  }
  state.viewer.frameLoading = false;
  if (!state.viewer.running) return;
  if (state.viewer.pendingFrame) {
    state.viewer.pendingFrame = false;
    scheduleViewerFrame(80);
    return;
  }
  scheduleViewerFrame(260);
}

async function startViewer() {
  const serial = $("viewerSerial").value;
  if (!serial) {
    toast("Choose an online ADB device first.", "bad");
    return;
  }
  if (state.viewer.running && state.viewer.serial === serial) {
    stopViewer();
    return;
  }
  stopViewer();
  state.viewer.running = true;
  state.viewer.serial = serial;
  setSelectedSerial(serial);
  state.viewer.size = null;
  state.viewer.frameWidth = 0;
  state.viewer.frameHeight = 0;
  state.viewer.lastUrl = "";
  $("launchViewerBtn").textContent = "Stop viewer";
  viewerStatus("Connecting...");
  $("viewerFrame").scrollIntoView({ block: "center", behavior: "smooth" });
  $("viewerBody").focus({ preventScroll: true });
  refreshViewerFrame();
  api(`/api/viewer/size?serial=${encodeURIComponent(serial)}`).then((size) => {
    if (state.viewer.serial === serial) state.viewer.size = size.width && size.height ? size : null;
  }).catch(() => {
    if (state.viewer.serial === serial) state.viewer.size = null;
  });
}

function viewerPointFromEvent(event) {
  const img = $("viewerImage");
  if (img.classList.contains("hidden")) return null;
  const rect = img.getBoundingClientRect();
  const naturalWidth = state.viewer.size?.width || state.viewer.frameWidth || img.naturalWidth || rect.width;
  const naturalHeight = state.viewer.size?.height || state.viewer.frameHeight || img.naturalHeight || rect.height;
  const imageAspect = naturalWidth / naturalHeight;
  const boxAspect = rect.width / rect.height;
  let drawWidth = rect.width;
  let drawHeight = rect.height;
  let offsetX = 0;
  let offsetY = 0;
  if (boxAspect > imageAspect) {
    drawWidth = rect.height * imageAspect;
    offsetX = (rect.width - drawWidth) / 2;
  } else {
    drawHeight = rect.width / imageAspect;
    offsetY = (rect.height - drawHeight) / 2;
  }
  const localX = event.clientX - rect.left - offsetX;
  const localY = event.clientY - rect.top - offsetY;
  if (localX < 0 || localY < 0 || localX > drawWidth || localY > drawHeight) return null;
  const x = Math.max(0, Math.min(Math.round((localX / drawWidth) * naturalWidth), Math.round(naturalWidth - 1)));
  const y = Math.max(0, Math.min(Math.round((localY / drawHeight) * naturalHeight), Math.round(naturalHeight - 1)));
  const bodyRect = $("viewerBody").getBoundingClientRect();
  return { x, y, markerX: event.clientX - bodyRect.left, markerY: event.clientY - bodyRect.top };
}

function showViewerMarker(point) {
  const marker = $("viewerTouchMarker");
  if (!point || !marker) return;
  marker.style.left = `${point.markerX}px`;
  marker.style.top = `${point.markerY}px`;
  marker.classList.remove("hidden");
  marker.classList.add("active");
  if (state.viewer.markerTimer) clearTimeout(state.viewer.markerTimer);
  state.viewer.markerTimer = setTimeout(hideViewerMarker, 520);
}

function hideViewerMarker() {
  const marker = $("viewerTouchMarker");
  if (!marker) return;
  marker.classList.remove("active");
  if (state.viewer.markerTimer) clearTimeout(state.viewer.markerTimer);
  state.viewer.markerTimer = setTimeout(() => marker.classList.add("hidden"), 180);
}

async function sendViewerTapPoint(point) {
  if (!state.viewer.running || !$("viewerControl").checked || !point) return;
  showViewerMarker(point);
  state.viewer.tapHoldUntil = Date.now() + 1200;
  viewerStatus(`Tap ${point.x}, ${point.y}`);
  try {
    await api("/api/viewer/tap", { method: "POST", body: JSON.stringify({ serial: state.viewer.serial, x: point.x, y: point.y }) });
    scheduleViewerFrame(80);
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function sendViewerSwipePoint(start, end, duration) {
  if (!state.viewer.running || !$("viewerControl").checked || !start || !end) return;
  showViewerMarker(end);
  state.viewer.tapHoldUntil = Date.now() + 1400;
  viewerStatus(`Swipe ${start.x},${start.y} -> ${end.x},${end.y}`);
  try {
    await api("/api/viewer/swipe", { method: "POST", body: JSON.stringify({ serial: state.viewer.serial, x1: start.x, y1: start.y, x2: end.x, y2: end.y, duration }) });
    scheduleViewerFrame(100);
  } catch (error) {
    toast(error.message, "bad");
  }
}

function viewerPointerDown(event) {
  if (!state.viewer.running || !$("viewerControl").checked) return;
  const point = viewerPointFromEvent(event);
  if (!point) return;
  event.preventDefault();
  $("viewerBody").focus({ preventScroll: true });
  $("viewerBody").setPointerCapture?.(event.pointerId);
  state.viewer.pointer = { id: event.pointerId, start: point, last: point, startedAt: Date.now() };
  showViewerMarker(point);
  viewerStatus(`Touch ${point.x}, ${point.y}`);
}

function viewerPointerMove(event) {
  const pointer = state.viewer.pointer;
  if (!pointer || pointer.id !== event.pointerId) return;
  const point = viewerPointFromEvent(event);
  if (!point) return;
  event.preventDefault();
  pointer.last = point;
  showViewerMarker(point);
}

function viewerPointerUp(event) {
  const pointer = state.viewer.pointer;
  if (!pointer || pointer.id !== event.pointerId) return;
  const end = viewerPointFromEvent(event) || pointer.last;
  state.viewer.pointer = null;
  $("viewerBody").releasePointerCapture?.(event.pointerId);
  const dx = end.x - pointer.start.x;
  const dy = end.y - pointer.start.y;
  const distance = Math.hypot(dx, dy);
  const duration = Math.max(80, Math.min(Date.now() - pointer.startedAt, 1200));
  if (distance > 18) {
    sendViewerSwipePoint(pointer.start, end, duration).catch(() => {});
  } else {
    sendViewerTapPoint(end).catch(() => {});
  }
}

function viewerPointerCancel(event) {
  if (state.viewer.pointer?.id === event.pointerId) state.viewer.pointer = null;
  hideViewerMarker();
}

async function sendViewerKey(key) {
  if (!state.viewer.serial) return;
  await flushViewerText();
  try {
    await api("/api/viewer/key", { method: "POST", body: JSON.stringify({ serial: state.viewer.serial, key }) });
    scheduleViewerFrame(80);
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function sendViewerText(text) {
  if (!state.viewer.serial || !text) return;
  try {
    await api("/api/viewer/text", { method: "POST", body: JSON.stringify({ serial: state.viewer.serial, text }) });
    state.viewer.tapHoldUntil = Date.now() + 900;
    viewerStatus(`Typed ${text.length} character${text.length === 1 ? "" : "s"}`);
    scheduleViewerFrame(70);
  } catch (error) {
    toast(error.message, "bad");
  }
}

function queueViewerText(text) {
  if (!state.viewer.running || !$("viewerControl").checked || !text) return;
  state.viewer.textBuffer += text;
  state.viewer.tapHoldUntil = Date.now() + 900;
  viewerStatus("Typing...");
  if (state.viewer.textTimer) clearTimeout(state.viewer.textTimer);
  state.viewer.textTimer = setTimeout(() => flushViewerText().catch(() => {}), 110);
}

async function flushViewerText() {
  if (state.viewer.textTimer) clearTimeout(state.viewer.textTimer);
  state.viewer.textTimer = null;
  const text = state.viewer.textBuffer;
  state.viewer.textBuffer = "";
  if (text) await sendViewerText(text);
}

function viewerKeyAction(key) {
  const map = {
    Enter: "ENTER",
    Backspace: "DEL",
    Tab: "TAB",
    ArrowUp: "DPAD_UP",
    ArrowDown: "DPAD_DOWN",
    ArrowLeft: "DPAD_LEFT",
    ArrowRight: "DPAD_RIGHT",
    Escape: "BACK",
  };
  return map[key] || "";
}

function viewerKeyDown(event) {
  if (!state.viewer.running || !$("viewerControl").checked) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const action = viewerKeyAction(event.key);
  if (action) {
    event.preventDefault();
    sendViewerKey(action).catch(() => {});
    return;
  }
  if (event.key && event.key.length === 1) {
    event.preventDefault();
    queueViewerText(event.key);
  }
}

function globalViewerKeyDown(event) {
  if (!state.viewer.running || state.page !== "work") return;
  const tag = String(document.activeElement?.tagName || "").toLowerCase();
  if (["input", "textarea", "select", "button"].includes(tag)) return;
  viewerKeyDown(event);
}

function viewerPaste(event) {
  if (!state.viewer.running || !$("viewerControl").checked) return;
  const text = event.clipboardData?.getData("text") || "";
  if (!text) return;
  event.preventDefault();
  queueViewerText(text);
  flushViewerText().catch(() => {});
}

function renderJobs() {
  $("jobsList").innerHTML = state.jobs.length ? state.jobs.map(jobCard).join("") : `<div class="empty-state"><h3>No jobs yet</h3><p>Run setup or proof actions to see logs.</p></div>`;
}

function renderSettings(config, backups = []) {
  const keys = ["MODE", "NUM_DEVICES", "WSL_DISTRO", "WSL_USERNAME", "REDROID_IMAGE", "CHROME_APK", "REDROID_BASE_PORT"];
  $("configForm").innerHTML = keys.map((key) => `
    <div class="form-field">
      <label for="cfg-${key}">${key}</label>
      <input class="input" id="cfg-${key}" name="${key}" value="${escapeHtml(config[key] ?? "")}">
    </div>
  `).join("");
  const restoreBtn = $("restoreConfigBtn");
  if (restoreBtn) {
    restoreBtn.disabled = backups.length === 0;
    restoreBtn.title = backups.length ? "Restore the newest UI-created config backup" : "No UI-created backups yet";
  }
  const status = $("configBackupStatus");
  if (status) {
    status.textContent = backups.length
      ? `Latest backup: ${backups[0].name}`
      : "No UI-created config backups yet.";
  }
}

async function refreshCaptures() {
  const data = await api("/api/captures");
  state.captures = data.captures || [];
  $("clearCapturesBtn").disabled = state.captures.length === 0;
  $("captureGallery").innerHTML = state.captures.length ? state.captures.map((cap) => {
    const thumb = cap.type === "png" ? `<img src="${escapeHtml(cap.url)}" alt="${escapeHtml(cap.name)}">` : `<div class="capture-thumb">${escapeHtml(cap.type.toUpperCase())}</div>`;
    return `<a class="capture-card" href="${escapeHtml(cap.url)}" target="_blank" rel="noreferrer">${thumb}<div class="capture-meta">${escapeHtml(cap.name)}</div></a>`;
  }).join("") : `<div class="empty-state"><h3>No captures yet</h3><p>Run screenshots, recordings, or stealth checks to build this page.</p></div>`;
}

async function clearCaptures(button) {
  const confirmed = await confirmAction("clear-captures");
  if (!confirmed) return;
  setButtonBusy(button, true);
  try {
    const data = await api("/api/captures/clear", { method: "POST", body: JSON.stringify({}) });
    toast(`Cleared ${data.removed || 0} gallery item(s)`, "ok");
    await refreshCaptures();
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    setButtonBusy(button, false);
    if (button?.id === "clearCapturesBtn") button.disabled = state.captures.length === 0;
  }
}

async function clearLogs(button) {
  const confirmed = await confirmAction("clear-logs");
  if (!confirmed) return;
  setButtonBusy(button, true);
  try {
    const data = await api("/api/jobs/clear", { method: "POST", body: JSON.stringify({}) });
    state.jobs = data.jobs || [];
    state.selectedJob = null;
    state.selectedJobDetail = null;
    renderJobs();
    showJobResult(null);
    $("activeJobNotice")?.classList.add("hidden");
    $("jobLog").textContent = "No job selected.";
    $("logHint").textContent = "Select a job to inspect output.";
    toast(`Cleared ${data.removed || 0} finished log(s)`, "ok");
  } catch (error) {
    toast(error.message, "bad");
  } finally {
    setButtonBusy(button, false);
  }
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'"'"'`)}'`;
}

function nativeViewerCommand(serial) {
  const cwd = state.health?.env?.cwd || ".";
  const env = state.health?.env || {};
  const size = $("viewerMaxSize")?.value?.trim() || "";
  const serialForCommand = env.is_windows && serial?.startsWith("wsl:") ? serial.slice(4) : serial;
  const parts = ["python", "-m", "damru", "view"];
  if (serialForCommand) parts.push("--serial", serialForCommand);
  if (size) parts.push("--max-size", size);
  if (env.is_windows) {
    const quoted = parts.map((part) => part.includes(" ") ? `"${part.replace(/"/g, "\\\"")}"` : part).join(" ");
    return `cd /d "${cwd.replace(/"/g, "\\\"")}" && ${quoted}`;
  }
  return `cd ${shellQuote(cwd)} && ${parts.map(shellQuote).join(" ")}`;
}

async function copyNativeViewerCommand(button) {
  const serial = $("viewerSerial").value || $("taskSerial").value || state.selectedSerial;
  if (!serial) {
    toast("Choose an ADB worker first.", "bad");
    return;
  }
  const command = nativeViewerCommand(serial);
  setButtonBusy(button, true);
  try {
    await navigator.clipboard.writeText(command);
  } catch {
    const area = document.createElement("textarea");
    area.value = command;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  } finally {
    setButtonBusy(button, false);
  }
  toast("Native viewer command copied. Paste it in a new terminal for faster scrcpy viewing.", "ok");
}

async function refreshAll() {
  const tasks = [
    api("/api/jobs").then((jobs) => {
      state.jobs = jobs.jobs || [];
      renderJobs();
      updateActiveJobNotice();
      return "jobs";
    }),
    api("/api/workers").then((workers) => {
      state.workers = workers.workers || [];
      state.adb = workers.adb_devices || [];
      renderWorkers();
      return "workers";
    }),
    api("/api/health").then((health) => {
      state.health = health;
      renderHealth();
      return "health";
    }),
    api("/api/config").then((data) => {
      state.config = data.config || {};
      state.configBackups = data.backups || [];
      if (state.health) renderSettings(state.config, state.configBackups);
      return "config";
    }),
  ];
  const results = await Promise.allSettled(tasks);
  renderWorkers();
  refreshSelectedJobResult().catch(() => {});
  refreshOpenDrawer().catch(() => {});
  const failed = results.find((result) => result.status === "rejected");
  if (failed && failed.status === "rejected") throw failed.reason;
}

async function openJob(id) {
  const job = await api(`/api/jobs/${id}`);
  state.selectedJob = id;
  $("jobLog").textContent = job.log || "No output.";
  $("logHint").textContent = `${job.name} (${job.status})`;
  $("drawerLogTitle").textContent = `${job.name} (${job.status})`;
  $("drawerJobLog").textContent = job.log || "No output.";
  if (state.page === "logs") {
    $("logDrawer").classList.add("hidden");
  } else {
    $("logDrawer").classList.remove("hidden");
  }
}

async function refreshOpenDrawer() {
  if (!state.selectedJob || $("logDrawer").classList.contains("hidden")) return;
  const job = await api(`/api/jobs/${state.selectedJob}`);
  $("drawerLogTitle").textContent = `${job.name} (${job.status})`;
  $("drawerJobLog").textContent = job.log || "No output.";
  $("jobLog").textContent = job.log || "No output.";
  $("logHint").textContent = `${job.name} (${job.status})`;
}

function bindEvents() {
  $("refreshBtn").addEventListener("click", () => refreshAll().then(() => toast("Status refreshed", "ok")).catch((e) => toast(e.message, "bad")));
  $("nextActionBtn").addEventListener("click", (event) => {
    event.stopPropagation();
    const action = $("nextActionBtn").dataset.action;
    if (action === "workers") return showPage("workers");
    if (!action || action === "none") return showPage("setup");
    runAction(action, {}, event.currentTarget).catch(() => {});
  });
  document.body.addEventListener("click", (event) => {
    if (event.target.closest("#toggleHealthChecks")) {
      state.showPassingChecks = !state.showPassingChecks;
      renderHealth();
      return;
    }
    const sectionBtn = event.target.closest("[data-scroll-target]");
    if (sectionBtn) {
      setSelectedSerial(sectionBtn.dataset.selectSerial || "");
      showPage(sectionBtn.dataset.page || "work");
      const target = $(sectionBtn.dataset.scrollTarget);
      target?.scrollIntoView({ block: "start", behavior: "smooth" });
      if (sectionBtn.dataset.scrollTarget === "viewerPanel") {
        startViewer().catch((e) => toast(e.message, "bad"));
      }
      if (sectionBtn.dataset.autoproof === "1") {
        runAction("proof", { serial: sectionBtn.dataset.selectSerial || state.selectedSerial, proxy: $("taskProxy")?.value || "" }, sectionBtn).catch(() => {});
      }
      return;
    }
    const pageBtn = event.target.closest("[data-page]");
    if (pageBtn) {
      setSelectedSerial(pageBtn.dataset.selectSerial || "");
      showPage(pageBtn.dataset.page);
      return;
    }
    const workerBtn = event.target.closest("[data-worker-action]");
    if (workerBtn) {
      const actionMap = { restart: "restart-worker", stop: "stop-worker", resume: "resume-worker", delete: "delete-worker", "fix-internet": "fix-internet", "random-profile": "random-profile" };
      const action = actionMap[workerBtn.dataset.workerAction] || "stop-worker";
      const payload = ["fix-internet", "random-profile"].includes(action) ? { serial: workerBtn.dataset.serial || "" } : { index: workerBtn.dataset.index };
      if (action === "random-profile") payload.proxy = $("taskProxy")?.value || "";
      const row = workerBtn.closest("tr");
      runAction(action, payload, workerBtn).then(() => {
        if (action === "delete-worker") row?.remove();
        setTimeout(() => refreshAll().catch(() => {}), 1200);
      }).catch(() => {});
      return;
    }
    const actionBtn = event.target.closest("[data-action]");
    if (actionBtn) {
      if (actionBtn.dataset.action === "workers") return showPage("workers");
      runAction(actionBtn.dataset.action, {}, actionBtn).catch(() => {});
      return;
    }
    const jobBtn = event.target.closest("[data-job]");
    if (jobBtn) openJob(jobBtn.dataset.job).catch((e) => toast(e.message, "bad"));
  });
  $("workerSearch").addEventListener("input", renderWorkers);
  $("taskSerial").addEventListener("change", (event) => {
    setSelectedSerial(event.currentTarget.value);
    switchViewerSerialFast(event.currentTarget.value);
  });
  $("viewerSerial").addEventListener("change", (event) => {
    setSelectedSerial(event.currentTarget.value);
    switchViewerSerialFast(event.currentTarget.value);
  });
  $("reloadCapturesBtn").addEventListener("click", () => refreshCaptures().catch((e) => toast(e.message, "bad")));
  $("clearCapturesBtn").addEventListener("click", (event) => clearCaptures(event.currentTarget).catch((e) => toast(e.message, "bad")));
  $("openUrlBtn").addEventListener("click", (event) => {
    const url = $("taskUrl").value.trim();
    if (!/^https?:\/\//i.test(url)) {
      toast("Enter a URL that starts with http:// or https://.", "bad");
      $("taskUrl").focus();
      return;
    }
    runAction("navigate", { serial: $("taskSerial").value, url, proxy: $("taskProxy").value }, event.currentTarget).catch(() => {});
  });
  $("fixInternetBtn").addEventListener("click", (event) => runAction("fix-internet", { serial: $("taskSerial").value }, event.currentTarget).catch(() => {}));
  $("randomProfileBtn").addEventListener("click", (event) => runAction("random-profile", { serial: $("taskSerial").value, proxy: $("taskProxy").value }, event.currentTarget).catch(() => {}));
  $("randomProfileAllBtn").addEventListener("click", (event) => runAction("random-profile", { all: true, proxy: $("taskProxy").value }, event.currentTarget).catch(() => {}));
  $("quickCheckBtn").addEventListener("click", (event) => runAction("quick-check", { serial: $("taskSerial").value }, event.currentTarget).catch(() => {}));
  $("screenshotBtn").addEventListener("click", (event) => runAction("screenshot", { serial: $("taskSerial").value }, event.currentTarget).catch(() => {}));
  $("runProofBtn").addEventListener("click", (event) => runAction("proof", { serial: $("taskSerial").value, proxy: $("taskProxy").value }, event.currentTarget).catch(() => {}));
  $("runProofAllBtn").addEventListener("click", (event) => runAction("proof-all", { proxy: $("taskProxy").value }, event.currentTarget).catch(() => {}));
  $("addWorkerBtn").addEventListener("click", (event) => {
    const count = Number($("workerCount").value || 1);
    if (!Number.isInteger(count) || count < 1 || count > 50) {
      toast("Enter a worker count between 1 and 50.", "bad");
      $("workerCount").focus();
      return;
    }
    runAction("add-workers", { count }, event.currentTarget).catch(() => {});
  });
  $("startWorkersBtn").addEventListener("click", (event) => runAction("resume-workers", { count: Number($("workerCount").value || 0) }, event.currentTarget).catch(() => {}));
  $("fixInternetAllBtn").addEventListener("click", (event) => runAction("fix-internet", { all: true }, event.currentTarget).catch(() => {}));
  $("stopWorkersBtn").addEventListener("click", (event) => runAction("stop-workers", {}, event.currentTarget).catch(() => {}));
  $("deleteWorkersBtn").addEventListener("click", (event) => runAction("delete-workers", {}, event.currentTarget).catch(() => {}));
  $("launchViewerBtn").addEventListener("click", () => startViewer().catch((e) => toast(e.message, "bad")));
  $("copyNativeViewerBtn").addEventListener("click", (event) => copyNativeViewerCommand(event.currentTarget));
  $("viewerMaxSize").addEventListener("focus", () => toast("Max size is for native scrcpy command/video size. Lower value can feel faster.", "ok"));
  $("viewerBody").addEventListener("pointerdown", viewerPointerDown);
  $("viewerBody").addEventListener("pointermove", viewerPointerMove);
  $("viewerBody").addEventListener("pointerup", viewerPointerUp);
  $("viewerBody").addEventListener("pointercancel", viewerPointerCancel);
  $("viewerBody").addEventListener("keydown", viewerKeyDown);
  $("viewerBody").addEventListener("paste", viewerPaste);
  document.addEventListener("keydown", globalViewerKeyDown);
  document.querySelectorAll("[data-viewer-key]").forEach((button) => {
    button.addEventListener("click", () => sendViewerKey(button.dataset.viewerKey));
  });
  $("viewerSendTextBtn").addEventListener("click", async () => {
    const input = $("viewerTextInput");
    const text = input.value;
    if (!text) return;
    input.value = "";
    await sendViewerText(text);
    $("viewerBody").focus({ preventScroll: true });
  });
  $("viewerTextInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    $("viewerSendTextBtn").click();
  });
  $("viewerScreenshotBtn").addEventListener("click", (event) => runAction("screenshot", { serial: $("viewerSerial").value }, event.currentTarget).catch(() => {}));
  $("viewerRecordBtn").addEventListener("click", (event) => runAction("record", { serial: $("viewerSerial").value, time_limit: 15 }, event.currentTarget).catch(() => {}));
  $("saveConfigBtn").addEventListener("click", async () => {
    const updates = {};
    new FormData($("configForm")).forEach((value, key) => { updates[key] = value; });
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify({ updates }) });
      toast("Config saved with backup", "ok");
      await refreshAll();
    } catch (e) { toast(e.message, "bad"); }
  });
  $("reloadConfigBtn").addEventListener("click", () => refreshAll().catch((e) => toast(e.message, "bad")));
  $("restoreConfigBtn").addEventListener("click", async (event) => {
    const latest = state.configBackups?.[0];
    if (!latest) {
      toast("No UI-created config backup exists yet.", "bad");
      return;
    }
    const confirmed = await confirmAction("restore-config", { name: latest.name });
    if (!confirmed) return;
    setButtonBusy(event.currentTarget, true);
    try {
      await api("/api/config/restore", { method: "POST", body: JSON.stringify({ name: latest.name }) });
      toast("Config restored from latest backup", "ok");
      await refreshAll();
    } catch (e) {
      toast(e.message, "bad");
    } finally {
      setButtonBusy(event.currentTarget, false);
    }
  });
  $("kernelInstallBtn").disabled = false;
  $("kernelInstallBtn").addEventListener("click", (event) => {
    const phrase = $("wslPhrase").value.trim().toLowerCase();
    if (phrase !== "yes") {
      toast("Type yes first.", "bad");
      $("wslPhrase").focus();
      return;
    }
    runAction("wsl-kernel-install", { phrase }, event.currentTarget).catch(() => {});
  });
  $("closeLogDrawerBtn").addEventListener("click", () => $("logDrawer").classList.add("hidden"));
  $("copyLogBtn").addEventListener("click", async () => {
    const text = $("jobLog").textContent || $("drawerJobLog").textContent || "";
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    toast("Log copied", "ok");
  });
  $("clearLogsBtn").addEventListener("click", (event) => clearLogs(event.currentTarget).catch((e) => toast(e.message, "bad")));
}

async function start() {
  buildNav();
  bindEvents();
  window.addEventListener("popstate", () => showPage(pageFromPath(), false));
  showPage(pageFromPath(), false);
  try {
    await refreshAll();
  } catch (e) {
    toast(e.message, "bad");
  }
  state.poll = setInterval(() => refreshAll().catch(() => {}), 6000);
}

start();
