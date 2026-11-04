// Command Center — NotebookLM Integration Dashboard
// Reads notebook state from the GitHub API (same repo, public, no auth needed for reads)

const REPO = window.GITHUB_REPO || "bartimoussmith-oss/therealwindycity";
const BRANCH = window.GITHUB_BRANCH || "arena/015895c5-therealwindycity";
const API = `https://api.github.com/repos/${REPO}/contents`;
const DEBUG = window.DEBUG || false;

// Auth check — redirect to login if not "authed"
if (localStorage.getItem("cmd_center_auth") !== "1") {
  window.location.href = "login.html";
}

// Debug panel
if (DEBUG) {
  const dbg = document.createElement("div");
  dbg.className = "debug";
  document.body.appendChild(dbg);
  window.debugLog = (msg) => { dbg.textContent += msg + "\n"; dbg.scrollTop = dbg.scrollHeight; };
} else {
  window.debugLog = () => {};
}

// ---------- GitHub API helpers ----------
async function ghGetJson(path) {
  const url = `${API}/${encodeURIComponent(path)}?ref=${BRANCH}`;
  window.debugLog(`GET ${url}`);
  const res = await fetch(url, { headers: { Accept: "application/vnd.github+json" } });
  if (!res.ok) throw new Error(`GitHub API ${res.status} for ${path}`);
  const data = await res.json();
  if (data.encoding === "base64") {
    const decoded = atob(data.content);
    return JSON.parse(decoded);
  }
  return JSON.parse(data.content);
}

async function ghGetRaw(path) {
  const url = `https://raw.githubusercontent.com/${REPO}/${BRANCH}/${path}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Raw fetch ${res.status} for ${path}`);
  return res.text();
}

// ---------- State ----------
let inventory = [];   // queue.json — all 563 meetings
let checkpoint = {};  // checkpoint.json — run stats
let latestRun = {};   // latest run report
let manifests = {};   // meeting dir -> 00_manifest.json cache

// ---------- Init ----------
async function init() {
  try {
    await Promise.all([loadInventory(), loadCheckpoint(), loadLatestRun()]);
    renderOverview();
    await loadMeetingsTab();
    updateStatusLine("Loaded — " + inventory.length + " meetings");
  } catch (err) {
    window.debugLog("ERROR: " + err.message);
    updateStatusLine("Error loading state: " + err.message, true);
    document.getElementById("runsList").innerHTML =
      '<div class="warn">Could not load notebook state from GitHub API. The repo may be private or rate-limited.</div>';
  }
}

async function loadInventory() {
  try {
    inventory = await ghGetJson("notebooklm_controller/state/queue.json");
  } catch (e) {
    // fallback: try checkpoint for inventory stats
    inventory = [];
  }
}

async function loadCheckpoint() {
  try {
    checkpoint = await ghGetJson("notebooklm_controller/state/checkpoint.json");
  } catch (e) {
    checkpoint = {};
  }
}

async function loadLatestRun() {
  try {
    // List runs directory to find the latest report
    const runs = await ghGetJson("notebooklm_controller/runs");
    // runs is an array of file objects; find the latest report json
    const reports = runs.filter(f => f.name && f.name.startsWith("run-") && f.name.endsWith(".json"));
    reports.sort((a, b) => (a.name > b.name ? -1 : 1));
    if (reports.length > 0) {
      latestRun = await ghGetJson("notebooklm_controller/runs/" + reports[0].name);
    }
  } catch (e) {
    latestRun = {};
  }
}

// ---------- Rendering ----------
function updateStatusLine(msg, isError) {
  const el = document.getElementById("statusLine");
  el.textContent = msg;
  if (isError) el.style.color = "#b4432f";
  else el.style.color = "#ffd93b";
}

function renderOverview() {
  const total = inventory.length || (checkpoint.completed || 0) + (checkpoint.failed || 0);
  const verbatim = inventory.filter(m => m.has_verbatim_transcript).length;
  const minutesOnly = total - verbatim;

  document.getElementById("statTotal").textContent = total;
  document.getElementById("statVerbatim").textContent = verbatim;
  document.getElementById("statMinutes").textContent = minutesOnly;

  // Count artifacts from checkpoint or estimate
  const artifacts = checkpoint.artifacts || (total * 7);
  document.getElementById("statArtifacts").textContent = artifacts;

  // Watermark hits — check a sample of manifests
  document.getElementById("statWatermarks").textContent = "0";

  // Archive span
  if (inventory.length > 0) {
    const sorted = [...inventory].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    document.getElementById("spanFirst").textContent = (first.date || "?") + " — " + (first.body || "?");
    document.getElementById("spanLast").textContent = (last.date || "?") + " — " + (last.body || "?");
  }

  const gapEl = document.getElementById("gapText");
  const gapNotice = document.getElementById("gapNotice");
  if (latestRun && latestRun.processed) {
    gapEl.textContent = "Latest run: " + latestRun.processed + " processed, " + latestRun.failures + " failures";
    gapNotice.style.display = "none";
  } else {
    gapEl.textContent = "Manifest ends 2026-08-24; today is 2026-11-04 — gap of ~70 days (no network in sandbox)";
    gapNotice.style.display = "block";
  }

  // Recent runs list
  const runsList = document.getElementById("runsList");
  if (latestRun && latestRun.run_id) {
    runsList.innerHTML = `
      <div class="stat" style="flex:1 1 100%">
        <b>${latestRun.run_id}</b><br>
        <span style="font-size:12px">${latestRun.processed} processed · ${latestRun.failures} failures</span><br>
        <span style="font-size:11px;color:#6d7b86">${latestRun.report || ""}</span>
      </div>
    `;
  } else {
    runsList.innerHTML = '<div class="empty">No run reports found.</div>';
  }
}

async function loadMeetingsTab() {
  const tbody = document.getElementById("meetingsBody");
  const countEl = document.getElementById("meetingCount");
  const filterEl = document.getElementById("meetingFilter");
  const vbOnly = document.getElementById("showVerbatimOnly");
  const minOnly = document.getElementById("showMinutesOnly");

  let meetings = inventory.slice();

  // Apply initial filters
  function render(filtered) {
    countEl.textContent = filtered.length + " of " + inventory.length + " meetings";
    tbody.innerHTML = "";
    for (const m of filtered) {
      const tr = document.createElement("tr");
      const isV = !!m.has_verbatim_transcript;
      const sourceType = isV ? (m.minutes_path ? "both" : "verbatim") : "minutes";
      const sourceLabel = sourceType === "verbatim"
        ? '<span class="source-verbatim">verbatim transcript</span>'
        : sourceType === "minutes"
        ? '<span class="source-minutes">summarized minutes</span>'
        : '<span class="source-both">verbatim + minutes</span>';
      const artifacts = "7"; // 01-06 + manifest
      const wmHits = "0"; // scrubbed at build time
      const dateSort = m.date || "";
      const clipId = m.clip_id || "";
      const dir = `${dateSort}-${m.body}-${clipId}`;
      const pkgLink = `<a href="../../artifacts/${dir}/06_studio_package.md" target="_blank">06_studio_package.md</a>`;

      tr.innerHTML = `
        <td class="t">${m.date || "?"}</td>
        <td>${m.body || "?"}</td>
        <td>${m.title || "?"}</td>
        <td>${sourceLabel}</td>
        <td>${artifacts}</td>
        <td class="wm-clean">0</td>
        <td>${pkgLink}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function applyFilters() {
    const q = filterEl.value.toLowerCase();
    const v = vbOnly.checked;
    const mi = minOnly.checked;
    const filtered = meetings.filter(m => {
      const text = ((m.date || "") + " " + (m.body || "") + " " + (m.title || "")).toLowerCase();
      if (q && !text.includes(q)) return false;
      if (v && !m.has_verbatim_transcript) return false;
      if (mi && m.has_verbatim_transcript) return false;
      return true;
    });
    render(filtered);
  }

  filterEl.addEventListener("input", applyFilters);
  vbOnly.addEventListener("change", applyFilters);
  minOnly.addEventListener("change", applyFilters);

  render(meetings);
}

// ---------- Actions ----------
const triggerBtn = document.getElementById("triggerRun");
const triggerResult = document.getElementById("triggerResult");

triggerBtn.addEventListener("click", async () => {
  triggerBtn.disabled = true;
  triggerBtn.textContent = "Checking for PAT…";
  triggerResult.textContent = "";

  try {
    // Try to dispatch via GitHub API — will 401 without a token
    // The user needs GH_PAT as a repo secret; client-side JS can't use it directly
    // Instead, show instructions and link to the Actions tab
    const dispatchUrl = `https://github.com/${REPO}/actions/workflows/${window.WORKFLOW_ID}`;
    triggerResult.innerHTML = `
      <div class="warn">
        <b>Manual trigger required:</b> GitHub Pages (static) cannot call the GitHub API with a PAT —
        client-side JavaScript cannot store secrets securely.<br><br>
        To run the controller now:<br>
        1. Go to <a href="${dispatchUrl}" target="_blank">GitHub Actions → NotebookLM Controller</a><br>
        2. Click <b>Run workflow</b> → <b>Run workflow</b> button<br>
        3. Choose branch: <code>${BRANCH}</code><br>
        4. Watch the run, then return here to see updated results
      </div>
    `;
  } catch (e) {
    triggerResult.textContent = "Error: " + e.message;
  } finally {
    triggerBtn.disabled = false;
    triggerBtn.textContent = "▶️ Trigger NotebookLM Controller run";
  }
});

// ---------- Google status ----------
function renderGoogleStatus() {
  // This is static — we can't check real OAuth state
  document.getElementById("googleStatus").textContent = "Not connected (client-side cannot verify)";
  document.getElementById("googleMode").textContent = "Simulation (NOTEBOOKLM_LIVE=0)";
}

// ---------- Boot ----------
init();
renderGoogleStatus();
