const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const resultLabels = {
  "application-resume.md": "可投递简历",
  "match-report.md": "匹配报告",
  "growth-plan.md": "提升路线",
  "target-resume.md": "目标简历（不可投递）",
  "interview-prep.md": "面试准备",
  "failure-report.md": "失败报告",
  "unsafe-draft.md": "未通过安全检查的草稿",
  "run.json": "运行详情",
};
const graphNodes = [
  ["extract_requirements", "解析 JD", 5, 42], ["build_evidence_index", "证据索引", 103, 42],
  ["match_requirements", "要求匹配", 201, 42], ["generate_application_resume", "生成简历", 299, 42],
  ["verify_application_resume", "事实核验", 397, 42], ["analyze_gaps", "分析差距", 495, 42],
  ["generate_growth_plan", "提升路线", 593, 42], ["generate_target_resume", "目标简历", 691, 42],
  ["generate_interview_prep", "面试准备", 789, 42], ["human_review", "人工审核", 887, 42],
];
const nodeStages = {
  prepare_matching: "match_requirements", match_batch: "match_requirements",
  prepare_resume: "generate_application_resume", generate_section: "generate_application_resume",
  prepare_verification: "verify_application_resume", verify_section: "verify_application_resume",
  finalize_verification: "verify_application_resume",
};
function stageForNode(node) { return nodeStages[node] || node; }
const state = {
  csrf: "", run: null, events: [], eventSource: null, startedAt: null,
  lastEventId: 0, actionPending: false,
  nodeStates: Object.fromEntries(graphNodes.map(([id]) => [id, "pending"])),
  activeResult: "application-resume.md", reviewSource: "", refreshTimer: null,
};

function toast(message) {
  const item = document.createElement("div"); item.className = "toast"; item.textContent = message;
  $("#toast-region").append(item); setTimeout(() => item.remove(), 4200);
}
function value(id) { return $(id).value.trim(); }
function numberValue(id) { return Number(value(id)); }
function serviceSettings(service) {
  const settings = {
    base_url: value(`#${service}-base-url`) || null,
    api_key: value(`#${service}-api-key`) || null,
    model: value(`#${service}-model`),
    timeout_seconds: numberValue(`#${service}-timeout`),
    max_retries: numberValue(`#${service}-retries`),
    use_server_key: $(`#${service}-server-key`).checked,
  };
  if (service === "embedding") settings.dimensions = numberValue("#embedding-dimensions") || null;
  if (service === "llm") {
    settings.reasoning_effort = value("#llm-reasoning") || null;
    settings.max_output_tokens = numberValue("#llm-max-output");
    settings.context_window = numberValue("#llm-context-window") || null;
  }
  return settings;
}
function config() { return { llm: serviceSettings("llm"), embedding: serviceSettings("embedding"), demo: $("#demo-mode").checked }; }
function persistConfig() {
  localStorage.setItem("resume-workbench-config", JSON.stringify(config()));
}
function restoreConfig() {
  const raw = localStorage.getItem("resume-workbench-config"); if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    const fieldIds = {
      base_url: "base-url",
      model: "model",
      timeout_seconds: "timeout",
      max_retries: "retries",
    };
    for (const service of ["llm", "embedding"]) {
      for (const [field, elementId] of Object.entries(fieldIds)) {
        const element = $(`#${service}-${elementId}`);
        if (element && saved[service]?.[field] != null) element.value = saved[service][field];
      }
      if (saved[service]?.api_key != null) $("#" + service + "-api-key").value = saved[service].api_key;
      $(`#${service}-server-key`).checked = Boolean(saved[service]?.use_server_key);
    }
    if (saved.embedding?.dimensions) $("#embedding-dimensions").value = saved.embedding.dimensions;
    if (saved.llm && "reasoning_effort" in saved.llm) $("#llm-reasoning").value = saved.llm.reasoning_effort || "";
    if (saved.llm?.max_output_tokens) $("#llm-max-output").value = saved.llm.max_output_tokens;
    if (saved.llm?.context_window) $("#llm-context-window").value = saved.llm.context_window;
    $("#demo-mode").checked = Boolean(saved.demo);
  } catch { localStorage.removeItem("resume-workbench-config"); }
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== "GET") headers.set("X-Resume-CSRF", state.csrf);
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : data.message || `请求失败 (${response.status})`);
  return data;
}
async function bootstrap() {
  const response = await fetch("/api/bootstrap"); if (!response.ok) throw new Error("无法建立本地会话");
  state.csrf = (await response.json()).csrf_token;
  const lastRun = localStorage.getItem("resume-workbench-run");
  if (lastRun) { try { await loadRun(lastRun); } catch { localStorage.removeItem("resume-workbench-run"); } }
}
function updateFileLabel(inputId, outputId) {
  const files = [...$(inputId).files]; $(outputId).textContent = files.length ? files.map((file) => file.name).join(", ") : "未选择";
}
async function testService(service) {
  const indicator = $(`#${service}-state`); indicator.className = "connection-state"; indicator.textContent = "测试中…";
  const started = performance.now();
  try {
    const result = await api("/api/connections/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service, settings: serviceSettings(service) }),
    });
    indicator.classList.add("success"); indicator.textContent = `可用 · ${result.duration_ms}ms`;
    if (service === "llm" && result.context_window) {
      const labels = { manual: "手动设置", langchain_profile: "LangChain Profile", ollama_config: "Ollama 配置", ollama_model_capped: "Ollama 模型信息（保守限制）", conservative_default: "保守默认" };
      $("#llm-context-detection").textContent = `本次将使用 ${result.context_window} tokens · ${labels[result.context_source] || result.context_source}`;
    }
    persistConfig();
  } catch (error) {
    indicator.classList.add("error"); indicator.textContent = `失败 · ${Math.round(performance.now() - started)}ms`; toast(error.message);
  }
}
async function startRun() {
  const jd = $("#jd-file").files[0], resume = $("#resume-file").files[0];
  if (!jd || !resume) { toast("请选择 JD 和 Master Resume"); return; }
  const button = $("#start-run"); button.disabled = true; button.textContent = "正在创建…";
  const form = new FormData(); form.append("config", JSON.stringify(config())); form.append("jd", jd); form.append("resume", resume);
  for (const source of $("#sources-files").files) form.append("sources", source);
  try {
    state.run = await api("/api/runs", { method: "POST", body: form }); persistConfig();
    localStorage.setItem("resume-workbench-run", state.run.id); state.startedAt = Date.now();
    state.events = []; state.lastEventId = 0; showRun(); connectEvents(); startRefresh();
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = "开始运行"; }
}
function showRun() { $("#empty-state").classList.add("hidden"); $("#run-view").classList.remove("hidden"); renderRun(); }
function statusTitle(status) {
  return ({ preparing: "正在准备", running: "正在执行", waiting_review: "等待人工审核", approved: "运行已批准", rejected: "运行已拒绝", failed: "运行失败", cancelling: "正在终止", cancelled: "运行已终止", interrupted: "运行已中断" })[status] || status;
}
function renderRun() {
  if (!state.run) return;
  const contextConfig = state.run.config?.llm;
  if (contextConfig?.resolved_context_window) {
    $("#llm-context-detection").textContent = `当前 Run 使用 ${contextConfig.resolved_context_window} tokens · ${contextConfig.context_source}`;
  }
  $("#run-id").textContent = `RUN ${state.run.id}`; $("#run-title").textContent = statusTitle(state.run.status);
  $("#current-node").textContent = graphNodes.find(([id]) => id === stageForNode(state.run.current_node))?.[1] || statusTitle(state.run.status);
  if (state.run.error) {
    const error = state.run.error;
    const category = {
      timeout: "请求超时",
      authentication: "认证失败",
      model_not_found: "模型不存在",
      connection_refused: "连接被拒绝",
      incompatible_input: "Embedding 输入格式不兼容",
      context_length: "LLM 上下文长度不足",
      safety_gate: "事实安全未通过",
      cancelled: "任务已取消",
      workflow: "工作流失败",
    }[error.category] || error.type;
    const context = [
      error.service, error.model,
      error.timeout_seconds != null ? `${error.timeout_seconds}s` : null,
      error.base_url,
    ]
      .filter(Boolean).join(" · ");
    const guidance = error.category === "context_length"
      ? " · 应用已自动拆批；最小不可拆分内容仍超出窗口，可手动提高 Context window 后重试"
      : "";
    $("#current-summary").textContent = `${category}${context ? ` · ${context}` : ""}${guidance}`;
  } else if (state.events.length) {
    $("#current-summary").textContent = eventSummary(state.events[state.events.length - 1]);
  }
  const safetyFailure = state.run.error?.category === "safety_gate";
  $("#safety-failure").classList.toggle("hidden", !safetyFailure);
  $("#recovery-actions").classList.toggle(
    "hidden", safetyFailure || !["failed", "interrupted"].includes(state.run.status)
  );
  if (safetyFailure) {
    $("#safety-issues").replaceChildren(...(state.run.error.issues || []).map((issue) => {
      const item = document.createElement("li");
      item.textContent = issue.claim;
      const reason = document.createElement("small"); reason.textContent = issue.reason;
      item.append(reason); return item;
    }));
  }
  $("#cancel-run").disabled = state.actionPending || !["preparing", "running", "waiting_review"].includes(state.run.status);
  renderGraph(); renderResults();
}
function renderGraph() {
  const svg = $("#graph-svg"); svg.replaceChildren();
  const ns = "http://www.w3.org/2000/svg";
  graphNodes.slice(0, -1).forEach(([, , x, y], index) => {
    const next = graphNodes[index + 1]; const line = document.createElementNS(ns, "path");
    line.setAttribute("class", "edge"); line.setAttribute("d", `M ${x + 84} ${y + 26} L ${next[2]} ${next[3] + 26}`); svg.append(line);
  });
  const retry = document.createElementNS(ns, "path"); retry.setAttribute("class", "edge retry"); retry.setAttribute("d", "M 439 96 C 430 130 350 130 341 96"); svg.append(retry);
  graphNodes.forEach(([id, label, x, y]) => {
    const group = document.createElementNS(ns, "g"); group.setAttribute("class", `node ${state.nodeStates[id] || "pending"}`);
    const rect = document.createElementNS(ns, "rect"); rect.setAttribute("x", x); rect.setAttribute("y", y); rect.setAttribute("width", 84); rect.setAttribute("height", 52);
    const text = document.createElementNS(ns, "text"); text.setAttribute("x", x + 42); text.setAttribute("y", y + 31); text.textContent = label;
    group.append(rect, text); svg.append(group);
  });
  const completeCount = Object.values(state.nodeStates).filter((status) => ["complete", "waiting"].includes(status)).length;
  $("#progress-bar").style.width = `${Math.max(4, Math.round(completeCount / graphNodes.length * 100))}%`;
  $("#graph-list").innerHTML = graphNodes.map(([id, label]) => `<li>${label}：${state.nodeStates[id] || "pending"}</li>`).join("");
}
function connectEvents() {
  state.eventSource?.close();
  state.eventSource = new EventSource(`/api/runs/${state.run.id}/events?after=${state.lastEventId}`);
  state.eventSource.onmessage = onEvent;
  for (const type of ["node_started", "node_progress", "node_heartbeat", "node_completed", "node_failed", "review_required", "run_completed", "run_failed", "run_cancelled"]) state.eventSource.addEventListener(type, onEvent);
  state.eventSource.onerror = () => { $("#current-summary").textContent = "事件连接暂时中断，正在自动重连…"; };
}
function onEvent(message) {
  const event = JSON.parse(message.data);
  if (event.id <= state.lastEventId || state.events.some((item) => item.id === event.id)) return;
  state.lastEventId = event.id; state.events.push(event); state.events = state.events.slice(-30);
  if (event.node) {
    const mapped = event.status === "complete" ? "complete" : event.status === "failed" ? "failed" : event.status === "waiting" ? "waiting" : "running";
    state.nodeStates[stageForNode(event.node)] = mapped; state.run.current_node = event.node;
  }
  $("#current-summary").textContent = eventSummary(event); renderEvents(); renderRun();
  if (["review_required", "run_completed", "run_failed", "run_cancelled"].includes(event.type)) {
    state.eventSource?.close(); state.eventSource = null; loadRun(state.run.id);
  }
}
function renderEvents() {
  $("#event-list").innerHTML = state.events.slice(-5).reverse().map((event) => `<li><time>${new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}</time>${escapeHtml(eventSummary(event))}</li>`).join("");
}
function eventSummary(event) {
  if (event.type === "node_progress") {
    if (event.details?.phase === "safe_fallback") {
      return `模型输出无法可靠核验，已保留原章节并继续${event.details?.section ? ` · ${event.details.section}` : ""}`;
    }
    return event.details?.phase === "embedding_retrieval"
      ? "正在执行 Embedding 语义检索"
      : event.details?.batch_total
        ? `${event.details.phase === "generation" ? "正在分节生成简历" : event.details.phase === "verification" ? "正在分节核验简历" : "正在映射要求与证据"} · 第 ${event.details.batch_index}/${event.details.batch_total} 批`
        : "正在处理上下文批次";
  }
  if (event.type !== "node_heartbeat") return event.summary;
  const elapsed = Number(event.details?.elapsed_seconds || 0);
  const node = graphNodes.find(([id]) => id === stageForNode(event.node))?.[1] || event.node;
  return elapsed >= 30
    ? `${node}仍在调用模型 · 已等待 ${elapsed}s，程序仍在运行`
    : `${node}正在调用模型 · 已等待 ${elapsed}s`;
}
async function loadRun(runId) {
  state.run = await api(`/api/runs/${runId}`);
  state.events = state.run.events || [];
  state.lastEventId = Math.max(0, ...state.events.map((event) => Number(event.id) || 0));
  state.nodeStates = Object.fromEntries(graphNodes.map(([id]) => [id, "pending"]));
  for (const event of state.events) if (event.node) {
    state.nodeStates[stageForNode(event.node)] = event.status === "complete" ? "complete" : event.status === "failed" ? "failed" : event.status === "waiting" ? "waiting" : "running";
  }
  state.startedAt = Date.parse(state.run.created_at); showRun(); renderEvents();
  if (
    ["running", "preparing", "cancelling"].includes(state.run.status)
    && (!state.eventSource || state.eventSource.readyState === EventSource.CLOSED)
  ) connectEvents();
  else if (!["running", "preparing", "cancelling"].includes(state.run.status)) {
    state.eventSource?.close(); state.eventSource = null; clearInterval(state.refreshTimer);
  }
  return state.run;
}
function startRefresh() { clearInterval(state.refreshTimer); state.refreshTimer = setInterval(() => state.run && loadRun(state.run.id).catch(() => {}), 1800); }
function startNewRun() {
  state.eventSource?.close(); state.eventSource = null; clearInterval(state.refreshTimer);
  state.run = null; state.events = []; state.lastEventId = 0; state.startedAt = null;
  localStorage.removeItem("resume-workbench-run");
  $("#run-view").classList.add("hidden"); $("#empty-state").classList.remove("hidden");
  $(".setup-panel").classList.remove("collapsed");
}
function renderResults() {
  const results = state.run?.results || {}; $("#result-links").replaceChildren();
  for (const [name, label] of Object.entries(resultLabels)) if (name in results) {
    const button = document.createElement("button"); button.type = "button"; button.className = "result-link"; button.textContent = label; button.onclick = () => openReview(name); $("#result-links").append(button);
  }
  $("#result-status").textContent = Object.keys(results).length ? `${Object.keys(results).length} 项可查看` : "运行完成后可查看";
  if (state.run?.status === "waiting_review" && results["application-resume.md"]) $("#result-status").textContent = "等待你的审核";
}
function openReview(name) {
  const source = state.run.results[name] || "";
  state.activeResult = name; state.reviewSource = source;
  $("#review-view").classList.remove("hidden"); $("#review-run-id").textContent = `运行 ${state.run.id}`; $("#review-status").textContent = statusTitle(state.run.status);
  $("#markdown-source").value = source;
  renderTabs(); setReviewMode("render");
  const actionable = state.run.status === "waiting_review" && name === "application-resume.md";
  const safetyFailed = state.run.error?.category === "safety_gate";
  const aspirational = name === "target-resume.md";
  $("#review-actions").classList.toggle("hidden", !actionable);
  $("#markdown-source").readOnly = !actionable;
  const message = $("#review-state-message");
  message.className = safetyFailed || aspirational ? "danger" : "verified";
  message.textContent = safetyFailed
    ? "✕ 事实安全未通过"
    : aspirational ? "⚠ 目标版本不可直接投递"
    : actionable ? "等待你的审核" : "✓ 此文件可供查看";
  $("#review-help").textContent = safetyFailed
    ? "这是诊断产物，不能批准。请根据失败报告补充证据，或删除、弱化不受支持的内容后新建运行。"
    : aspirational
      ? "其中的 TARGET 内容尚无事实证据，只能用于理解能力目标和执行提升路线。"
    : actionable
      ? "源码模式可以编辑 Markdown。编辑后的内容在提交前需要重新核验。"
      : "此产物为只读内容，可在渲染和源码模式之间切换。";
}
function renderTabs() {
  $("#result-tabs").replaceChildren();
  for (const [name, label] of Object.entries(resultLabels)) if (name in state.run.results) {
    const button = document.createElement("button"); button.type = "button"; button.textContent = label; button.className = name === state.activeResult ? "active" : "";
    button.onclick = () => openReview(name); $("#result-tabs").append(button);
  }
}
function renderMarkdown() {
  const source = $("#markdown-source").value; state.reviewSource = source;
  if (state.activeResult === "run.json") { $("#markdown-preview").textContent = source; return; }
  const md = window.markdownit({ html: false, linkify: true, highlight(code, language) { try { return window.hljs.highlight(code, { language }).value; } catch { return escapeHtml(code); } } });
  $("#markdown-preview").innerHTML = window.DOMPurify.sanitize(md.render(source));
}
function setReviewMode(mode) {
  $$(".view-switch button").forEach((button) => button.classList.toggle("active", button.dataset.view === mode));
  $("#markdown-preview").classList.toggle("hidden", mode !== "render"); $("#markdown-source").classList.toggle("hidden", mode !== "source");
  if (mode === "render") renderMarkdown();
}
async function submitReview(action) {
  try {
    state.run = await api(`/api/runs/${state.run.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, resume_markdown: $("#markdown-source").value }) });
    $("#review-view").classList.add("hidden"); renderRun(); toast(action === "approve" ? "简历已批准" : "运行已拒绝");
  } catch (error) { toast(error.message); }
}
async function cancelRun() {
  if (state.actionPending || !state.run) return;
  state.actionPending = true; state.run.status = "cancelling"; renderRun();
  try {
    state.run = await api(`/api/runs/${state.run.id}/cancel`, { method: "POST" });
    state.eventSource?.close(); state.eventSource = null; clearInterval(state.refreshTimer); renderRun();
  } catch (error) { toast(error.message); }
  finally { state.actionPending = false; renderRun(); }
}
async function resumeRun() {
  if (state.actionPending) return;
  state.actionPending = true; $("#resume-run").disabled = true;
  try {
    state.run = await api(`/api/runs/${state.run.id}/resume`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config()),
    });
    state.startedAt = Date.now(); renderRun(); connectEvents(); toast("已从 checkpoint 恢复");
  } catch (error) { toast(error.message); }
  finally { state.actionPending = false; $("#resume-run").disabled = false; }
}
function escapeHtml(text) { return String(text).replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]); }

restoreConfig();
bootstrap().catch((error) => toast(error.message));
$$('#setup-content input:not([type="file"]), #setup-content select').forEach((element) => {
  element.addEventListener("input", persistConfig);
  element.addEventListener("change", persistConfig);
});
$$('[data-test-service]').forEach((button) => button.addEventListener("click", () => testService(button.dataset.testService)));
$("#start-run").addEventListener("click", startRun); $("#cancel-run").addEventListener("click", cancelRun);
$("#resume-run").addEventListener("click", resumeRun); $("#test-after-failure").addEventListener("click", () => testService(state.run?.error?.service === "embedding" ? "embedding" : "llm"));
$("#view-failure-report").addEventListener("click", () => openReview("failure-report.md"));
$("#new-run").addEventListener("click", startNewRun);
$("#jd-file").addEventListener("change", () => updateFileLabel("#jd-file", "#jd-file-name"));
$("#resume-file").addEventListener("change", () => updateFileLabel("#resume-file", "#resume-file-name"));
$("#sources-files").addEventListener("change", () => updateFileLabel("#sources-files", "#sources-file-name"));
$("#panel-toggle").addEventListener("click", () => { const panel = $(".setup-panel"); panel.classList.toggle("collapsed"); $("#panel-toggle").setAttribute("aria-expanded", String(!panel.classList.contains("collapsed"))); });
$("#close-review").addEventListener("click", () => $("#review-view").classList.add("hidden"));
$("#approve-review").addEventListener("click", () => submitReview("approve")); $("#reject-review").addEventListener("click", () => submitReview("reject"));
$$('.view-switch button').forEach((button) => button.addEventListener("click", () => setReviewMode(button.dataset.view)));
let renderTimer; $("#markdown-source").addEventListener("input", () => { clearTimeout(renderTimer); renderTimer = setTimeout(renderMarkdown, 180); });
setInterval(() => { if (!state.startedAt) return; const elapsed = (Date.now() - state.startedAt) / 1000; $("#elapsed").textContent = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${(elapsed % 60).toFixed(1).padStart(4, "0")}`; }, 100);
