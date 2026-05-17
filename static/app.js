const API = "/api";
let statuses = [];
let pollTimer = null;
let _currentKeyword = null;
let _currentPage = 1;
let _hasMore = false;
let _fetching = false;

// --- Tabs ---
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("tab-tracker").classList.toggle("hidden", tab !== "tracker");
    document.getElementById("tab-jobs").classList.toggle("hidden", tab !== "jobs");
    if (tab === "jobs") { clearBadge(); showCachedJobs(); }
  });
});

// --- Init ---
async function fetchStatuses() {
  statuses = await fetch(`${API}/statuses`).then(r => r.json());
  const sel = document.getElementById("statusSelect");
  const filterSel = document.getElementById("filterStatus");
  statuses.forEach(s => {
    sel.innerHTML += `<option value="${s}">${s}</option>`;
    filterSel.innerHTML += `<option value="${s}">${s}</option>`;
  });
}

// --- Tracker ---
async function loadApplications() {
  const status = document.getElementById("filterStatus").value;
  const type   = document.getElementById("filterType").value;
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (type)   params.set("type", type);
  const apps = await fetch(`${API}/applications?${params}`).then(r => r.json());
  renderTable(apps);
  renderStats(apps);
}

function renderStats(apps) {
  const counts = {};
  statuses.forEach(s => counts[s] = 0);
  apps.forEach(a => counts[a.status] = (counts[a.status] || 0) + 1);
  document.getElementById("stats").innerHTML =
    `<div class="stat-card"><div class="count">${apps.length}</div><div class="label">Total</div></div>` +
    statuses.map(s => `<div class="stat-card"><div class="count">${counts[s]||0}</div><div class="label">${s}</div></div>`).join("");
}

function renderTable(apps) {
  const tbody = document.getElementById("appBody");
  const empty = document.getElementById("emptyMsg");
  const table = document.getElementById("appTable");
  if (!apps.length) {
    tbody.innerHTML = "";
    table.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }
  table.classList.remove("hidden");
  empty.classList.add("hidden");
  tbody.innerHTML = apps.map(a => `
    <tr id="row-${a.id}">
      <td>${esc(a.company)}</td>
      <td>${esc(a.role)}</td>
      <td>${a.type}</td>
      <td>
        <span class="badge badge-${a.status}">
          <select class="status-select" onchange="updateStatus(${a.id}, this.value)">
            ${statuses.map(s => `<option value="${s}" ${s===a.status?"selected":""}>${s}</option>`).join("")}
          </select>
        </span>
      </td>
      <td>${a.date_applied}</td>
      <td>${esc(a.notes||"—")}</td>
      <td>${a.url ? `<a href="${esc(a.url)}" target="_blank" class="job-link">↗ Apply</a>` : "—"}</td>
      <td><button class="action-btn" onclick="deleteApp(${a.id})" title="Delete">🗑️</button></td>
    </tr>`).join("");
}

async function updateStatus(id, newStatus) {
  await fetch(`${API}/applications/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  loadApplications();
}

async function deleteApp(id) {
  if (!confirm("Delete this application?")) return;
  await fetch(`${API}/applications/${id}`, { method: "DELETE" });
  loadApplications();
}

// --- Modal ---
function openModal(prefill = {}) {
  const form = document.getElementById("appForm");
  form.reset();
  if (prefill.company) form.company.value = prefill.company;
  if (prefill.role)    form.role.value    = prefill.role;
  if (prefill.type)    form.type.value    = prefill.type;
  if (prefill.url)     form.url.value     = prefill.url;
  document.getElementById("modalTitle").textContent = prefill.company ? `Track: ${prefill.company}` : "Add Application";
  document.getElementById("modal").classList.remove("hidden");
}
function closeModal() { document.getElementById("modal").classList.add("hidden"); }

document.getElementById("appForm").addEventListener("submit", async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  await fetch(`${API}/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  closeModal();
  loadApplications();
  document.querySelector('[data-tab="tracker"]').click();
  showToast(`✅ Added ${data.company} to your tracker`);
});

document.getElementById("filterStatus").addEventListener("change", loadApplications);
document.getElementById("filterType").addEventListener("change", loadApplications);
document.getElementById("modal").addEventListener("click", e => { if (e.target===e.currentTarget) closeModal(); });
document.getElementById("filterProvince").addEventListener("change", () => window._jobResults && renderJobCards(window._jobResults));
document.getElementById("filterJobType").addEventListener("change", () => window._jobResults && renderJobCards(window._jobResults));

// --- Cached Jobs ---
async function showCachedJobs() {
  _currentKeyword = null;
  _currentPage = 1;
  _hasMore = false;
  if (_scrollObserver) _scrollObserver.disconnect();
  const data = await fetch(`${API}/jobs/cached`).then(r => r.json());
  updateLastFetched(data.last_fetched);
  if (data.jobs && data.jobs.length) {
    renderJobCards(data.jobs);
    await fetch(`${API}/jobs/seen`, { method: "POST" });
  } else {
    document.getElementById("jobsEmpty").classList.remove("hidden");
    document.getElementById("jobCards").innerHTML = "";
  }
}

async function pollCachedJobs() {
  try {
    const data = await fetch(`${API}/jobs/cached`).then(r => r.json());
    updateLastFetched(data.last_fetched);
    const newCount = data.new_count || 0;
    const isOnJobsTab = document.querySelector('[data-tab="jobs"]').classList.contains("active");
    if (newCount > 0 && !isOnJobsTab) {
      showBadge(newCount);
      showToast(`🔔 ${newCount} new jobs found!`);
    } else if (isOnJobsTab && data.jobs.length) {
      renderJobCards(data.jobs);
      await fetch(`${API}/jobs/seen`, { method: "POST" });
    }
  } catch {}
}

async function manualRefresh() {
  document.getElementById("lastUpdatedText").textContent = "Refreshing...";
  await fetch(`${API}/jobs/refresh`, { method: "POST" });
  showToast("🔄 Jobs refreshed!");
  await showCachedJobs();
}

function updateLastFetched(ts) {
  const el = document.getElementById("lastUpdatedText");
  if (!ts) { el.textContent = "Not yet fetched"; return; }
  const d = new Date(ts);
  el.textContent = `Last updated: ${d.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}`;
}

// --- Live Search + Pagination ---
async function searchJobs() {
  const kw = document.getElementById("jobKeyword").value.trim();
  if (!kw) return showCachedJobs();
  _currentKeyword = kw;
  _currentPage = 1;
  window._jobResults = [];
  document.getElementById("jobCards").innerHTML = "";
  document.getElementById("jobsEmpty").classList.add("hidden");
  setLoadMore(false);
  initScrollObserver();
  await fetchPage(false);
}

async function loadMoreJobs() {
  if (!_hasMore || _fetching) return;
  _currentPage++;
  await fetchPage(true);
}

async function fetchPage(append) {
  if (_fetching) return;
  _fetching = true;
  const loadingId = append ? "jobsLoadingMore" : "jobsLoading";
  document.getElementById(loadingId).classList.remove("hidden");
  setLoadMore(false);

  if (!append) {
    document.getElementById("jobCards").innerHTML = "";
    document.getElementById("jobsEmpty").classList.add("hidden");
    window._jobResults = [];
  }

  const url = `${API}/jobs/stream?keyword=${encodeURIComponent(_currentKeyword)}&page=${_currentPage}`;
  let receivedAny = false;

  try {
    const response = await fetch(url);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // keep incomplete chunk

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (payload === "[DONE]") break;
        try {
          const jobs = JSON.parse(payload);
          if (!jobs.length) continue;
          receivedAny = true;
          // Dedupe against existing
          const existing = new Set((window._jobResults || []).map(j => j.title + j.company));
          const fresh = jobs.filter(j => !existing.has(j.title + j.company));
          if (!fresh.length) continue;
          window._jobResults = (window._jobResults || []).concat(fresh);
          appendJobCards(fresh);
          document.getElementById(loadingId).classList.add("hidden");
        } catch {}
      }
    }
  } catch {}

  document.getElementById(loadingId).classList.add("hidden");
  if (!receivedAny && !append) {
    document.getElementById("jobsEmpty").classList.remove("hidden");
  }
  _hasMore = receivedAny;
  _fetching = false;
}

// --- Infinite Scroll ---
let _scrollObserver = null;

function initScrollObserver() {
  if (_scrollObserver) _scrollObserver.disconnect();
  const sentinel = document.getElementById("scrollSentinel");
  _scrollObserver = new IntersectionObserver(entries => {
    if (entries[0].isIntersecting && _hasMore && _currentKeyword) {
      loadMoreJobs();
    }
  }, { rootMargin: "200px" });
  _scrollObserver.observe(sentinel);
}

function setLoadMore(show) {
  _hasMore = show;
}

// --- Card rendering ---
function _cardHTML(j, idx) {
  return `
    <div class="job-card ${j.is_new ? 'is-new' : ''}">
      <div class="job-card-header">
        <div>
          <div class="job-title">${esc(j.title)}</div>
          <div class="job-meta">
            ${esc(j.company)} · ${esc(j.location)}
            <span class="source-tag">${j.source}</span>
            ${j.province && j.province !== 'Other' ? `<span class="province-tag">📍 ${j.province}</span>` : ''}
            ${j.posted_at ? `<span class="date-tag">📅 ${j.posted_at}</span>` : ''}
            ${j.is_new ? '<span class="new-tag">NEW</span>' : ''}
          </div>
        </div>
        <span class="type-badge ${j.type}">${j.type}</span>
      </div>
      <p class="job-desc">${esc(j.description || "No description available.")}</p>
      <div class="job-actions">
        <button class="btn-secondary" onclick="openDesc(${idx})">📄 Description</button>
        <a href="${esc(j.url)}" target="_blank" class="btn-secondary link-btn">↗ Open</a>
        <button class="btn-primary" onclick='trackJob(${JSON.stringify(JSON.stringify(j))})'>+ Track This</button>
      </div>
    </div>`;
}

function _applyFilters(jobs) {
  const province = document.getElementById("filterProvince").value;
  const jobType  = document.getElementById("filterJobType").value;
  return jobs.filter(j =>
    (!province || j.province === province) &&
    (!jobType  || j.type === jobType)
  );
}

function renderJobCards(jobs) {
  window._jobResults = jobs;
  const filtered = _applyFilters(jobs);
  document.getElementById("jobsEmpty").classList.add("hidden");
  document.getElementById("jobsLoading").classList.add("hidden");
  document.getElementById("jobsCount").textContent = `${filtered.length} of ${jobs.length} jobs`;

  if (!filtered.length) {
    document.getElementById("jobsEmpty").classList.remove("hidden");
    document.getElementById("jobCards").innerHTML = "";
    return;
  }
  document.getElementById("jobCards").innerHTML = filtered.map((j, i) => _cardHTML(j, jobs.indexOf(j))).join("");
}

function appendJobCards(jobs) {
  const filtered = _applyFilters(jobs);
  const offset = (window._jobResults || []).length - jobs.length;
  document.getElementById("jobCards").innerHTML += filtered.map((j) => _cardHTML(j, window._jobResults.indexOf(j))).join("");
  document.getElementById("jobsCount").textContent = `${window._jobResults.length} jobs`;
}

// --- Description Modal ---
function openDesc(i) {
  const j = window._jobResults[i];
  if (!j) return;
  document.getElementById("descTitle").textContent = j.title;
  document.getElementById("descCompany").textContent = `🏢 ${j.company}`;
  document.getElementById("descLocation").textContent = `📍 ${j.location}`;
  document.getElementById("descBody").textContent = j.description || "No description available.";
  document.getElementById("descLink").href = j.url;
  document.getElementById("descModal").classList.remove("hidden");
}
function closeDescModal() { document.getElementById("descModal").classList.add("hidden"); }
document.getElementById("descModal").addEventListener("click", e => { if (e.target===e.currentTarget) closeDescModal(); });

function trackJob(jsonStr) {
  const j = JSON.parse(jsonStr);
  openModal({ company: j.company, role: j.title, type: j.type, url: j.url });
}

// --- Badge & Toast ---
function showBadge(count) {
  const badge = document.getElementById("newJobsBadge");
  badge.textContent = count;
  badge.classList.remove("hidden");
}
function clearBadge() { document.getElementById("newJobsBadge").classList.add("hidden"); }

let toastTimer;
function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3500);
}

// --- Keyword Chips ---
async function loadKeywordChips() {
  const keywords = await fetch(`${API}/jobs/keywords`).then(r => r.json());
  const bar = document.querySelector(".job-search-bar");
  const chips = document.createElement("div");
  chips.className = "keyword-chips";
  chips.innerHTML = keywords.map(k =>
    `<button class="chip" onclick="document.getElementById('jobKeyword').value='${k}';searchJobs();document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));this.classList.add('active')">${k}</button>`
  ).join("");
  bar.after(chips);
}

function esc(str) {
  return String(str||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// --- Start ---
fetchStatuses().then(loadApplications);
loadKeywordChips();
showCachedJobs();
pollTimer = setInterval(pollCachedJobs, 30_000);
