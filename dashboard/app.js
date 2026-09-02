"use strict";

const app = {
  csrf: "",
  overview: null,
  selectedProject: localStorage.getItem("dr-os-project") || "",
  detail: null,
  selectedJob: "",
  poller: null,
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const safeUrl = (value) => String(value || "").startsWith("https://") ? String(value) : "#";

async function api(path, options = {}) {
  const config = {...options};
  config.headers = {"Accept": "application/json", ...(options.headers || {})};
  if (config.method === "POST") {
    config.headers["Content-Type"] = "application/json";
    config.headers["X-Research-CSRF"] = app.csrf;
  }
  const response = await fetch(path, config);
  const payload = await response.json().catch(() => ({error: `HTTP ${response.status}`}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function toast(message, type = "") {
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.textContent = message;
  $("toastRegion").appendChild(element);
  setTimeout(() => element.remove(), 5200);
}

function setBusy(button, busy, label = "处理中…") {
  if (!button) return;
  if (busy) {
    button.dataset.original = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.original || button.textContent;
    button.disabled = false;
  }
}

async function loadOverview(silent = false) {
  try {
    const overview = await api("/api/overview");
    app.overview = overview;
    app.csrf = overview.csrf;
    if (app.selectedProject && !overview.projects.some((item) => item.project === app.selectedProject)) app.selectedProject = "";
    if (!app.selectedProject && overview.projects.length) app.selectedProject = overview.projects[0].project;
    renderOverview();
    if (app.selectedProject) await loadProject(app.selectedProject, true);
    if (app.selectedJob) await loadJob(app.selectedJob, true);
  } catch (error) {
    $("connectionBadge").className = "badge bad";
    $("connectionBadge").textContent = "连接失败";
    if (!silent) toast(error.message, "error");
  }
}

function renderOverview() {
  const data = app.overview;
  const configured = data.configuration.ready;
  $("versionValue").textContent = data.version;
  $("projectCount").textContent = data.projects.length;
  $("activeJobs").textContent = data.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  $("connectionBadge").className = `badge ${configured ? "good" : "warn"}`;
  $("connectionBadge").textContent = configured ? "API 已就绪" : "需要配置 API";
  const select = $("projectSelect");
  select.innerHTML = data.projects.length
    ? data.projects.map((item) => `<option value="${esc(item.project)}" ${item.project === app.selectedProject ? "selected" : ""}>${esc(item.project)} · ${esc(item.gate || "完成")}</option>`).join("")
    : '<option value="">尚未创建项目</option>';
  $("emptyState").classList.toggle("hidden", data.projects.length > 0);
  $("projectWorkspace").classList.toggle("hidden", !app.selectedProject);
  renderProviders();
  renderJobs();
  syncConfigForm();
}

function syncConfigForm() {
  const config = app.overview.configuration;
  $("baseUrl").value = config.base_url || "";
  $("anthropicModel").value = config.anthropic_model || "";
  $("openaiModel").value = config.openai_model || "";
  $("strictModel").checked = config.strict_model_id !== false;
  $("apiKey").placeholder = config.key_configured ? "已在内存中配置；留空保持不变" : "输入 UUAPI API Key";
  $("tavilyKey").placeholder = config.tavily_configured ? "已配置；留空保持不变" : "可选";
}

function renderProviders() {
  const current = new Set([...$("providerOptions").querySelectorAll("input:checked")].map((item) => item.value));
  const useCurrent = current.size > 0;
  $("providerOptions").innerHTML = app.overview.data_providers.map((provider) => `
    <label class="provider-option">
      <input type="checkbox" value="${esc(provider.id)}" ${(useCurrent ? current.has(provider.id) : true) ? "checked" : ""}>
      <span><strong>${esc(provider.name)}</strong><small>${esc(provider.description)}</small></span>
    </label>`).join("");
  $("sourceCountBadge").textContent = `${app.overview.data_providers.length} 个官方来源`;
  updateSearchScale();
}

async function loadProject(slug, silent = false) {
  try {
    app.detail = await api(`/api/projects/${encodeURIComponent(slug)}`);
    renderProject();
  } catch (error) {
    if (!silent) toast(error.message, "error");
  }
}

function renderProject() {
  const detail = app.detail;
  if (!detail) return;
  const state = detail.state;
  $("projectStatusBadge").className = `badge ${state.status === "approved" ? "good" : state.status === "invalid" ? "bad" : "warn"}`;
  $("projectStatusBadge").textContent = state.status;
  $("gateBadge").textContent = state.gate || "✓";
  $("nextActionTitle").textContent = state.next_action;
  $("nextActionCopy").textContent = stageAdvice(state);
  const alert = $("gateAlert");
  alert.classList.toggle("hidden", state.gate_error_count === 0);
  alert.textContent = state.gate_error_count ? `当前还有 ${state.gate_error_count} 项硬性要求未满足。运行模型不代表可以批准，请查看右侧缺项。` : "";
  renderStages(state);
  renderMetrics(detail.metrics);
  $("gateErrors").innerHTML = state.gate_errors.length
    ? state.gate_errors.map((error) => `<li>${esc(error)}</li>`).join("")
    : '<li class="muted">当前确定性检查没有发现缺项；仍需人工阅读内容。</li>';
  const awaitingWork = state.status === "awaiting_work";
  $("runCycle").disabled = !awaitingWork;
  $("markReady").disabled = state.status !== "awaiting_work" || !state.gate_ready;
  $("approveGate").disabled = state.status !== "awaiting_approval";
  $("reopenGate").disabled = state.status !== "awaiting_approval";
  $("advanceGate").disabled = state.status !== "approved";
  $("venueId").innerHTML = '<option value="">选择已安装期刊配置</option>' + detail.venues.map((venue) => `<option value="${esc(venue)}">${esc(venue)}</option>`).join("");
  renderDataReports(detail.data_reports);
}

function stageAdvice(state) {
  const advice = {
    "intake": "补全真实时间、预算、设备、研究目标和伦理边界；未知项必须保持未知。",
    "topic-intelligence": "检索候选方向、最近工作、反证和原创性风险，再选择博士主线。",
    "paper-architecture": "检查六篇论文的独立问题、证据和全部两两差异，拒绝切香肠。",
    "experiment-design": "为每篇论文锁定数据、基线、统计、种子、预算与证伪规则。",
    "experiment-execution": "先运行批准的实验，再根据真实输出建立 claim–evidence matrix。",
    "writing-and-review": `只处理当前论文 ${state.active_paper || ""}；正文、图表标签与投稿材料全部使用英文。`,
    "submission-ready": "逐篇生成 ZIP，检查 PDF/DOCX、当前 JCR 证据和期刊门户要求后手动投稿。",
  };
  return advice[state.stage] || "根据闸门缺项修复当前项目。";
}

function renderStages(state) {
  const labels = {"intake":"约束", "topic-intelligence":"选题", "paper-architecture":"论文架构", "experiment-design":"实验设计", "experiment-execution":"实验执行", "writing-and-review":"写作审查", "submission-ready":"投稿准备"};
  $("stageProgress").innerHTML = app.overview.stages.map((stage, index) => {
    const css = index < state.stage_index ? "done" : index === state.stage_index ? "current" : "future";
    return `<div class="stage ${css}"><strong>${esc(stage.gate || "完成")}</strong><span>${esc(labels[stage.name] || stage.name)}</span></div>`;
  }).join("");
}

function renderMetrics(metrics) {
  const items = [
    ["API 调用批次", metrics.api_runs],
    ["累计输入 Token", Number(metrics.input_tokens || 0).toLocaleString()],
    ["累计输出 Token", Number(metrics.output_tokens || 0).toLocaleString()],
    ["数据清单", metrics.dataset_manifests],
    ["实验尝试", metrics.experiment_attempts],
    ["论文完成", `${metrics.papers_ready}/${metrics.paper_count}`],
  ];
  $("metricGrid").innerHTML = items.map(([label, value]) => `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
}

function renderDataReports(reports) {
  if (!reports.length) {
    $("dataSummary").textContent = "尚未执行搜索";
    $("candidateRows").innerHTML = '<tr><td colspan="5" class="empty-cell">搜索完成后在这里比较候选数据</td></tr>';
    return;
  }
  const report = reports[0];
  const threshold = Number($("scoreFilter").value);
  const candidates = report.candidates.filter((item) => Number(item.metadata_relevance_score || 0) >= threshold);
  $("dataSummary").textContent = `${report.candidate_count} 个去重候选 · ${report.queries.filter(Boolean).length} 组查询 · 当前显示 ${candidates.length} 个`;
  $("candidateRows").innerHTML = candidates.length ? candidates.map(candidateRow).join("") : '<tr><td colspan="5" class="empty-cell">没有达到当前相关度阈值的候选</td></tr>';
}

function candidateRow(item) {
  const providers = item.also_found_by?.length ? item.also_found_by : [item.provider];
  const description = String(item.description || "暂无描述").slice(0, 260);
  const doi = item.doi ? `<span class="meta-line">DOI: ${esc(item.doi)}</span>` : "";
  const license = item.license_claim ? `<span class="meta-line">许可声明: ${esc(item.license_claim)}</span>` : '<span class="meta-line">许可证元数据缺失</span>';
  return `<tr>
    <td><span class="score-pill">${esc(item.metadata_relevance_score ?? 0)}</span></td>
    <td><a class="dataset-title" href="${esc(safeUrl(item.landing_url))}" target="_blank" rel="noopener noreferrer">${esc(item.title)}</a><div class="dataset-desc">${esc(description)}</div></td>
    <td><div class="source-tags">${providers.map((name) => `<span class="source-tag">${esc(name)}</span>`).join("")}</div></td>
    <td>${doi}${license}<span class="meta-line">匹配查询: ${esc((item.matched_queries || []).length)}</span></td>
    <td class="status-candidate">候选<br>需科学与人工审查</td>
  </tr>`;
}

function renderJobs() {
  if (!app.overview) return;
  const jobs = app.overview.jobs;
  $("jobList").innerHTML = jobs.length ? jobs.map((job) => `<button class="job-chip ${job.job_id === app.selectedJob ? "active" : ""}" data-job="${esc(job.job_id)}"><strong>${statusIcon(job.status)} ${esc(job.label)}</strong><span>${esc(job.status)} · ${esc(job.created_at)}</span></button>`).join("") : '<span class="muted">尚无任务。模型运行、数据搜索和实验都会在这里出现。</span>';
  const selected = jobs.find((job) => job.job_id === app.selectedJob);
  $("cancelJob").disabled = !selected || !["queued", "running"].includes(selected.status);
  document.querySelectorAll("[data-job]").forEach((button) => button.addEventListener("click", () => {
    app.selectedJob = button.dataset.job;
    loadJob(app.selectedJob);
    renderJobs();
  }));
}

function statusIcon(status) {
  return {queued:"◌", running:"●", succeeded:"✓", failed:"!", cancelled:"×"}[status] || "·";
}

async function loadJob(jobId, silent = false) {
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    $("jobLog").textContent = job.log || "任务尚未产生输出。";
    $("jobLog").scrollTop = $("jobLog").scrollHeight;
    if (["succeeded", "failed", "cancelled"].includes(job.status) && !silent) toast(`${job.label}：${job.status}`, job.status === "succeeded" ? "success" : "error");
  } catch (error) {
    if (!silent) toast(error.message, "error");
  }
}

async function startJob(action, values = {}) {
  const payload = await api("/api/jobs", {method: "POST", body: JSON.stringify({action, ...values})});
  app.selectedJob = payload.job.job_id;
  toast(`${payload.job.label} 已进入任务队列`, "success");
  await loadOverview(true);
  return payload.job;
}

function currentProject() {
  if (!app.selectedProject) throw new Error("请先选择项目");
  return app.selectedProject;
}

function gateValues() {
  return {project: currentProject(), actor: $("approvalActor").value, note: $("gateNote").value};
}

function updateSearchScale() {
  const queryCount = $("dataQueries").value.split(/\n/).filter((item) => item.trim()).length;
  const providerCount = $("providerOptions").querySelectorAll("input:checked").length;
  const limit = Number($("dataLimit").value || 0);
  $("searchScale").textContent = `${(queryCount * providerCount * limit).toLocaleString()} 条元数据（去重前上限）`;
}

function bindEvents() {
  $("openConfig").addEventListener("click", () => $("configDialog").showModal());
  $("closeConfig").addEventListener("click", () => $("configDialog").close());
  $("refreshButton").addEventListener("click", () => loadOverview());
  $("projectSelect").addEventListener("change", async (event) => {
    app.selectedProject = event.target.value;
    localStorage.setItem("dr-os-project", app.selectedProject);
    $("projectWorkspace").classList.toggle("hidden", !app.selectedProject);
    if (app.selectedProject) await loadProject(app.selectedProject);
  });
  $("configForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("saveConfig"); setBusy(button, true);
    try {
      await api("/api/config", {method:"POST", body: JSON.stringify({api_key:$("apiKey").value, base_url:$("baseUrl").value, anthropic_model:$("anthropicModel").value, openai_model:$("openaiModel").value, tavily_key:$("tavilyKey").value, strict_model_id:$("strictModel").checked})});
      $("apiKey").value = ""; $("tavilyKey").value = "";
      toast("API 配置已保存到当前进程内存", "success");
      $("configDialog").close(); await loadOverview(true);
    } catch (error) { toast(error.message, "error"); } finally { setBusy(button, false); }
  });
  $("checkHealth").addEventListener("click", () => startJob("health").catch((e) => toast(e.message, "error")));
  $("liveProbe").addEventListener("click", () => { if (confirm("这会分别进行一次小额计费调用。继续吗？")) startJob("health", {live:true}).catch((e) => toast(e.message, "error")); });
  $("checkBalance").addEventListener("click", () => startJob("balance").catch((e) => toast(e.message, "error")));
  $("startForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { app.selectedProject = $("startProject").value; localStorage.setItem("dr-os-project", app.selectedProject); await startJob("start", {project:app.selectedProject, context:$("startContext").value}); } catch (error) { toast(error.message, "error"); }
  });
  $("cycleForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await startJob("cycle", {project:currentProject(), context:$("cycleContext").value, discovery_query:$("discoveryQuery").value, max_output_tokens:Number($("maxTokens").value)}); } catch (error) { toast(error.message, "error"); }
  });
  [["gateCheck","gate_check"],["markReady","ready"],["approveGate","approve"],["advanceGate","advance"],["reopenGate","reopen"]].forEach(([id, action]) => $(id).addEventListener("click", () => startJob(action, gateValues()).catch((e) => toast(e.message, "error"))));
  $("dataSearchForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const providers = [...$("providerOptions").querySelectorAll("input:checked")].map((item) => item.value);
    try { await startJob("data_search", {project:currentProject(), queries:$("dataQueries").value, providers, limit:Number($("dataLimit").value)}); } catch (error) { toast(error.message, "error"); }
  });
  $("providerOptions").addEventListener("change", updateSearchScale);
  $("dataQueries").addEventListener("input", updateSearchScale);
  $("dataLimit").addEventListener("input", updateSearchScale);
  $("scoreFilter").addEventListener("input", () => { $("scoreValue").textContent = $("scoreFilter").value; if (app.detail) renderDataReports(app.detail.data_reports); });
  $("clearJobSelection").addEventListener("click", () => { app.selectedJob = ""; $("jobLog").textContent = "选择一个任务查看实时输出。"; renderJobs(); });
  $("cancelJob").addEventListener("click", async () => {
    if (!app.selectedJob || !confirm("停止任务可能留下未完成的模型调用或实验记录。确定停止吗？")) return;
    try {
      await api(`/api/jobs/${encodeURIComponent(app.selectedJob)}/cancel`, {method:"POST", body:"{}"});
      toast("已经请求停止任务", "success");
      await loadOverview(true);
    } catch (error) { toast(error.message, "error"); }
  });
  $("runExperiment").addEventListener("click", () => startJob("experiment", {project:currentProject(), run_id:$("experimentRun").value}).catch((e) => toast(e.message, "error")));
  $("validateDataset").addEventListener("click", () => startJob("dataset_validate", {project:currentProject(), manifest:$("datasetManifest").value}).catch((e) => toast(e.message, "error")));
  $("downloadDataset").addEventListener("click", () => startJob("dataset_download", {project:currentProject(), manifest:$("datasetManifest").value, accept_license:$("acceptLicense").checked}).catch((e) => toast(e.message, "error")));
  $("buildPackage").addEventListener("click", () => startJob("package", {project:currentProject(), paper:$("packagePaper").value}).catch((e) => toast(e.message, "error")));
  $("setVenue").addEventListener("click", () => startJob("set_venue", {project:currentProject(), paper:$("venuePaper").value, venue:$("venueId").value}).catch((e) => toast(e.message, "error")));
}

bindEvents();
loadOverview();
app.poller = setInterval(() => loadOverview(true), 3000);
