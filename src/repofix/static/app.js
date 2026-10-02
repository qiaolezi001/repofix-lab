"use strict";

const $ = (id) => document.getElementById(id);
let currentTask = null;
let tasks = [];
let polling = false;
const runningStatuses = new Set(["queued", "running", "pending", "created"]);
const terminalStatuses = new Set(["succeeded", "success", "completed", "failed", "timed_out", "timeout", "cancelled", "diagnosed", "blocked"]);
const statusNames = {queued: "等待执行", running: "执行中", pending: "等待执行", created: "已创建", succeeded: "执行完成", success: "执行完成", completed: "执行完成", failed: "执行失败", timed_out: "任务超时", timeout: "任务超时", cancelled: "已取消", diagnosed: "诊断完成", blocked: "执行受阻", interrupted: "可恢复", paused: "可恢复"};
const eventNames = {created: "任务已创建", started: "开始执行", status: "状态变化", tool: "工具调用", tool_request: "工具调用", tool_result: "工具返回", model: "模型调用", model_request: "模型调用", model_error: "模型错误", model_result: "模型返回", verification_requested: "请求完整公开验证", verification_result: "公开验证结果", checkpoint: "保存执行状态", completed: "执行完成", finished: "执行完成", error: "执行错误", cancelled: "任务取消", resumed: "任务恢复", interrupted: "执行中断", decision: "决策摘要"};

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body); } catch (_) { /* response may not be JSON */ }
    throw new Error(message);
  }
  return response.json();
}
function alertError(error) { $("alert").textContent = error.message || String(error); $("alert").hidden = false; }
function clearAlert() { $("alert").hidden = true; }
function announce(text) { $("announcement").textContent = text; }
function stringify(value) { return typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2); }
function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
function badgeClass(status) { if (["succeeded", "success", "completed", "diagnosed"].includes(status)) return "good"; if (["failed", "timed_out", "timeout", "blocked"].includes(status)) return "bad"; if (runningStatuses.has(status)) return "pending"; return ""; }
function formattedTime(value) { if (!value) return "—"; const date = new Date(value); return isNaN(date.getTime()) ? String(value).slice(11, 19) : date.toLocaleTimeString("zh-CN", {hour12: false}); }

async function loadHealth() {
  const health = await api("/api/health");
  const docker = health.docker || {};
  const available = ["available", "ready", "ok"].includes(docker.status) || docker.available === true;
  $("docker-dot").className = `status-dot ${available ? "available" : "unavailable"}`;
  $("docker-label").textContent = available ? "Docker 测试环境可用" : "Docker 测试环境不可用";
  $("docker-details").textContent = available ? "默认关闭网络 · 限制资源" : "仍可检索、诊断和导出候选补丁；测试尚未验证";
  $("docker-details").title = stringify(docker.details || docker);
  $("model-label").textContent = `${health.mode === "live" ? "LIVE" : "MOCK"} / ${health.model || "deterministic"}`;
  $("model-label").title = $("model-label").textContent;
}
async function loadTasks() {
  const result = await api("/api/tasks");
  tasks = Array.isArray(result) ? result : result.tasks || [];
  renderTaskList();
}
function renderTaskList() {
  const container = $("task-list"); container.replaceChildren();
  if (!tasks.length) { container.append(element("p", "subtle sidebar-empty", "暂无任务。载入示例，开始第一次实验。")); return; }
  for (const task of tasks) {
    const button = element("button", `history-item${currentTask?.id === task.id ? " active" : ""}`);
    button.append(element("span", "history-issue", task.issue || task.summary || task.id));
    const meta = element("span", "history-meta"); meta.append(element("span", "", (task.mode || "mock").toUpperCase()), element("span", "", statusNames[task.status] || task.status));
    button.append(meta); button.addEventListener("click", () => selectTask(task.id)); container.append(button);
  }
}
async function selectTask(id) {
  try { clearAlert(); const task = await api(`/api/tasks/${encodeURIComponent(id)}`); renderTask(task); renderTaskList(); } catch (error) { alertError(error); }
}
function showNewTask() {
  currentTask = null; $("detail").hidden = true; $("welcome").hidden = false; $("composer").hidden = false; renderTaskList(); $("source").focus(); clearAlert();
}
function renderTask(task) {
  const previousStatus = currentTask?.status; currentTask = task;
  $("detail").hidden = false; $("welcome").hidden = true;
  $("task-id").textContent = `02 / RUN ${task.id}`;
  $("detail-title").textContent = task.strategy === "baseline" ? "单次补丁执行记录" : "Agent 执行记录";
  $("detail-issue").textContent = task.issue || "";
  $("task-mode").textContent = (task.mode || "mock").toUpperCase(); $("task-mode").className = `badge ${task.mode === "live" ? "live" : "mock"}`;
  $("task-status").textContent = statusNames[task.status] || task.status; $("task-status").className = `badge ${badgeClass(task.status)}`;
  $("cancel-task").hidden = !runningStatuses.has(task.status);
  $("resume-task").hidden = !["interrupted", "paused"].includes(task.status);
  $("summary").textContent = task.summary || (runningStatuses.has(task.status) ? "任务正在执行。工具结果与补丁将在这里更新。" : "执行已结束，详细结果见下方轨迹。");
  $("task-error").hidden = !task.error; $("task-error").textContent = task.error ? stringify(task.error) : "";
  const usage = task.usage || {};
  $("metric-calls").textContent = usage.model_calls ?? usage.calls ?? 0;
  const tokenTotal = usage.total_tokens ?? ((usage.prompt_tokens ?? usage.input_tokens ?? 0) + (usage.completion_tokens ?? usage.output_tokens ?? 0));
  $("metric-tokens").textContent = task.mode === "mock" ? "模拟 / 0" : (usage.tokens_known === false || usage.total_tokens == null && !usage.prompt_tokens && !usage.input_tokens ? "未知" : Number(tokenTotal).toLocaleString());
  const seconds = usage.elapsed_seconds ?? usage.duration_seconds ?? task.elapsed_seconds;
  $("metric-time").textContent = seconds != null ? `${Number(seconds).toFixed(1)} s` : "—";
  const independent = task.independent_tests || task.independent_evaluation;
  $("metric-independent").textContent = independent?.status === "passed" ? "独立验收通过" : independent?.status === "failed" ? "独立验收失败" : "尚未测量";
  $("report-md").href = `/api/tasks/${encodeURIComponent(task.id)}/report?format=md`;
  $("report-json").href = `/api/tasks/${encodeURIComponent(task.id)}/report?format=json`;
  renderEvidence(task.evidence || []); renderDiff(task.candidate_patch || ""); renderTests(task.public_tests || {}); renderEvents(task.events || []); renderPipeline(task); renderVerification(task);
  if (previousStatus !== task.status) announce(`任务${statusNames[task.status] || task.status}`);
}
function renderEvidence(evidence) {
  const container = $("evidence-list"); container.replaceChildren(); $("evidence-count").textContent = evidence.length;
  if (!evidence.length) { container.append(element("p", "empty-output", "尚未检索到代码证据。Agent 读取或检索代码后将在这里列出引用。")); return; }
  evidence.forEach((item) => {
    const card = element("article", "evidence-card");
    const top = element("div", "evidence-top");
    const start = item.start_line ?? item.line_start ?? item.start ?? "?"; const end = item.end_line ?? item.line_end ?? item.end ?? start;
    top.append(element("strong", "", `${item.path || item.file || "unknown"}:${start}–${end}`), element("span", "", item.symbol || "module"));
    card.append(top, element("pre", "code-block", item.text || item.code || item.content || "无代码片段"));
    card.append(element("div", "evidence-meta", `版本 ${String(item.version || item.workspace_version || currentTask?.workspace_version || "未知").slice(0, 16)}${item.score != null ? ` · BM25 ${Number(item.score).toFixed(3)}` : ""}`));
    container.append(card);
  });
}
function renderDiff(patch) {
  const container = $("diff"); container.replaceChildren(); $("download-patch").disabled = !patch;
  if (!patch) { container.textContent = "暂未生成补丁。"; return; }
  for (const line of patch.split("\n")) { const className = line.startsWith("+") && !line.startsWith("+++") ? "diff-added" : line.startsWith("-") && !line.startsWith("---") ? "diff-deleted" : line.startsWith("@@") || line.startsWith("diff ") ? "diff-heading" : ""; const node = element("span", className, line + "\n"); container.append(node); }
}
function renderTests(tests) {
  const summary = $("test-summary"); summary.replaceChildren();
  const status = tests.status || (tests.passed === true ? "passed" : tests.passed === false ? "failed" : "not_run");
  const labels = {passed: "公开测试通过", failed: "公开测试失败", unavailable: "Docker 不可用 · 测试尚未验证", not_run: "公开测试尚未运行", timeout: "测试执行超时", timed_out: "测试执行超时", error: "测试执行错误", skipped: "测试未执行"};
  const label = status === "passed" && !tests.complete_suite ? "所选测试通过 · 完整套件尚未通过" : labels[status] || status;
  summary.append(element("span", `badge ${status === "passed" ? "good" : ["failed", "error", "timeout", "timed_out"].includes(status) ? "bad" : "pending"}`, label));
  if (tests.exit_code != null) summary.append(element("span", "subtle mono", `exit ${tests.exit_code}`));
  $("test-output").textContent = tests.output || tests.stdout || tests.details || tests.message || (Object.keys(tests).length ? stringify(tests) : "尚未运行公开测试。Docker 不可用时，候选补丁不会被标为通过测试。");
}
function renderVerification(task) {
  const container = $("verification"); container.replaceChildren();
  const publicPassed = task.public_tests?.status === "passed" && task.public_tests?.complete_suite === true;
  container.append(element("span", task.candidate_patch ? "verified" : "", task.candidate_patch ? "✓ 已提出候选修复" : "○ 尚未提出候选修复"));
  container.append(element("span", publicPassed ? "verified" : "", publicPassed ? "✓ 公开测试通过" : "○ 公开测试尚未通过"));
  const independent = task.independent_tests || task.independent_evaluation;
  container.append(element("span", independent?.status === "passed" ? "verified" : "", independent?.status === "passed" ? "✓ 独立验收通过" : independent?.status === "failed" ? "○ 独立验收失败" : "○ 独立验收尚未测量"));
}
function renderEvents(events) {
  const container = $("events"); container.replaceChildren();
  if (!events.length) { container.append(element("li", "subtle", "等待执行事件…")); return; }
  for (const event of events) {
    const li = element("li", ""); const time = element("time", "", formattedTime(event.at)); time.dateTime = event.at || "";
    const content = element("div", ""); const data = event.data || {};
    const description = data.tool || data.name || data.status || data.summary || (typeof data === "string" ? data : "");
    content.append(element("strong", "", `${eventNames[event.kind] || event.kind}${description ? ` · ${String(description).slice(0, 140)}` : ""}`));
    if (Object.keys(data).length) { const details = element("details", ""); details.append(element("summary", "", "查看执行数据"), element("pre", "", stringify(data))); content.append(details); }
    li.append(time, element("span", "event-dot"), content); container.append(li);
  }
}
function renderPipeline(task) {
  let stage = task.candidate_patch ? 1 : 0;
  if (task.public_tests && Object.keys(task.public_tests).length) stage = 2;
  if (terminalStatuses.has(task.status)) stage = 3;
  document.querySelectorAll(".pipeline li").forEach((node, index) => { node.className = index < stage ? "done" : index === stage ? (terminalStatuses.has(task.status) ? "done" : "active") : ""; });
}
function selectTab(name, focus = false) {
  document.querySelectorAll("[data-tab]").forEach((tab) => { const selected = tab.dataset.tab === name; tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1; $(`panel-${tab.dataset.tab}`).hidden = !selected; if (selected && focus) tab.focus(); });
}
function modeChanged() {
  const live = $("mode").value === "live"; $("paid-panel").hidden = !live;
  $("mode-note").replaceChildren(element("span", `badge ${live ? "live" : "mock"}`, live ? "LIVE" : "MOCK"), document.createTextNode(live ? "模型通过服务器配置调用。费用与成功率依提供商和任务而定。" : "确定性演示只验证工程流程，不能证明模型修复能力。"));
  $("paid-budget").textContent = $("strategy").value === "baseline" ? "1" : "8";
  $("allow-paid").checked = false;
}
async function submitTask(event) {
  event.preventDefault(); clearAlert();
  const live = $("mode").value === "live";
  if (live && !$("allow-paid").checked) { alertError(new Error("请先确认允许本次真实模型调用，或选择 Mock 离线演示。")); return; }
  $("submit-task").disabled = true;
  try { const task = await api("/api/tasks", {method: "POST", body: JSON.stringify({source: $("source").value.trim(), issue: $("issue").value.trim(), mode: $("mode").value, strategy: $("strategy").value, allow_paid: live && $("allow-paid").checked, limits: {max_model_calls: $("strategy").value === "baseline" ? 1 : 8}})}); renderTask(task); await loadTasks(); $("detail").scrollIntoView({behavior: "smooth", block: "start"}); } catch (error) { alertError(error); } finally { $("submit-task").disabled = false; }
}
async function taskAction(action) {
  if (!currentTask) return;
  const button = $(`${action}-task`); button.disabled = true;
  try { clearAlert(); const task = await api(`/api/tasks/${encodeURIComponent(currentTask.id)}/${action}`, {method: "POST"}); renderTask(action === "resume" && task.status === "interrupted" ? {...task, status: "running"} : task); await loadTasks(); } catch (error) { alertError(error); } finally { button.disabled = false; }
}
$("task-form").addEventListener("submit", submitTask);
$("mode").addEventListener("change", modeChanged); $("strategy").addEventListener("change", modeChanged);
$("load-demo").addEventListener("click", async () => { try { clearAlert(); const demo = await api("/api/demo"); $("source").value = demo.source; $("issue").value = demo.issue; $("mode").value = "mock"; $("strategy").value = "agent"; modeChanged(); announce("离线示例已载入，可以启动修复。"); $("issue").focus(); } catch (error) { alertError(error); } });
$("refresh-tasks").addEventListener("click", () => loadTasks().catch(alertError)); $("new-task").addEventListener("click", showNewTask);
$("cancel-task").addEventListener("click", () => taskAction("cancel")); $("resume-task").addEventListener("click", () => taskAction("resume"));
$("download-patch").addEventListener("click", () => { if (!currentTask?.candidate_patch) return; const url = URL.createObjectURL(new Blob([currentTask.candidate_patch], {type: "text/plain"})); const anchor = element("a", ""); anchor.href = url; anchor.download = `repofix-${currentTask.id}.patch`; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
document.querySelectorAll("[data-tab]").forEach((tab) => { tab.addEventListener("click", () => selectTab(tab.dataset.tab)); tab.addEventListener("keydown", (event) => { const tabs = [...document.querySelectorAll("[data-tab]")]; let index = tabs.indexOf(tab); if (event.key === "ArrowRight") index = (index + 1) % tabs.length; else if (event.key === "ArrowLeft") index = (index - 1 + tabs.length) % tabs.length; else if (event.key === "Home") index = 0; else if (event.key === "End") index = tabs.length - 1; else return; event.preventDefault(); selectTab(tabs[index].dataset.tab, true); }); });
async function poll() { if (polling || document.hidden || !currentTask || !runningStatuses.has(currentTask.status)) return; polling = true; try { const task = await api(`/api/tasks/${encodeURIComponent(currentTask.id)}`); renderTask(task); if (!runningStatuses.has(task.status)) await loadTasks(); } catch (error) { alertError(error); } finally { polling = false; } }
setInterval(poll, 1200);
Promise.allSettled([loadHealth(), loadTasks()]).then((results) => results.forEach((result) => { if (result.status === "rejected") alertError(result.reason); }));
