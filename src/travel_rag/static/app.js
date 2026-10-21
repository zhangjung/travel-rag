const form = document.querySelector("#plan-form");
const submitButton = document.querySelector("#submit-button");
const buttonLabel = submitButton.querySelector(".button-label");
const statusEl = document.querySelector("#status");
const formStatusDot = document.querySelector(".form-status .status-dot");
const emptyEl = document.querySelector("#empty-state");
const loadingEl = document.querySelector("#loading-state");
const loadingTitleEl = document.querySelector("#loading-title");
const resultEl = document.querySelector("#result");
const requestIdEl = document.querySelector("#request-id");
const savePlanButton = document.querySelector("#save-plan");
const downloadMarkdownButton = document.querySelector("#download-markdown");
const tabs = [...document.querySelectorAll(".tab")];
const panels = [...document.querySelectorAll(".tab-panel")];
const pipelineSteps = [...document.querySelectorAll("#runtime-pipeline li")];
let latestPlanResponse = null;
let currentSavedPlanId = null;

const metrics = {
  destination: document.querySelector("#metric-destination"),
  days: document.querySelector("#metric-days"),
  budget: document.querySelector("#metric-budget"),
  citations: document.querySelector("#metric-citations"),
  review: document.querySelector("#metric-review"),
};

const splitValues = (value = "") =>
  value
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);

const escapeHtml = (value = "") =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const safeUrl = (value) => {
  if (!value) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
};

const formatCurrency = (value) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);

const listMarkup = (items, fallback = "暂无") => {
  if (!Array.isArray(items) || items.length === 0) {
    return `<p>${escapeHtml(fallback)}</p>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
};

const sourceLabel = {
  case: "历史案例",
  experience: "旅行经验",
  realtime: "实时信息",
};

const freshnessLabel = {
  stable: "稳定知识",
  seasonal: "季节信息",
  realtime: "实时信息",
};

function activateTab(name) {
  tabs.forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  panels.forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (index + direction + tabs.length) % tabs.length;
    tabs[nextIndex].focus();
    activateTab(tabs[nextIndex].dataset.tab);
  });
});

function setPipeline(activeIndex, state = "running") {
  pipelineSteps.forEach((step, index) => {
    step.classList.remove("is-active", "is-complete", "is-error");
    const marker = step.querySelector("i");
    marker.textContent = String(index + 1);
    if (state === "complete" || index < activeIndex) {
      step.classList.add("is-complete");
      marker.textContent = "✓";
    } else if (index === activeIndex) {
      step.classList.add(state === "error" ? "is-error" : "is-active");
      marker.textContent = state === "error" ? "!" : String(index + 1);
    }
  });
}

function setIdleMetrics(payload = {}) {
  metrics.destination.textContent = payload.destination || "--";
  metrics.days.textContent = payload.days ? `${payload.days} 天` : "-- 天";
  metrics.budget.textContent = payload.budget_cny
    ? formatCurrency(payload.budget_cny)
    : "--";
  metrics.citations.textContent = "-- 条";
  metrics.review.textContent = "待审核";
}

function renderItinerary(body) {
  const schedule = Array.isArray(body.itinerary?.schedule)
    ? body.itinerary.schedule
    : [];
  const days = schedule
    .map((day) => {
      const evidence = (day.evidence_ids || [])
        .map((id) => `<span class="evidence-badge">引用 ${escapeHtml(id)}</span>`)
        .join("");
      return `
        <article class="day-card">
          <div class="day-marker">
            <strong>D${escapeHtml(day.day)}</strong>
            <small>第 ${escapeHtml(day.day)} 天</small>
          </div>
          <div class="day-body">
            <div class="day-title-row">
              <h3>${escapeHtml(day.theme)}</h3>
              <span class="cost-badge">${formatCurrency(day.estimated_cost_cny)}</span>
            </div>
            <div class="activity-list">
              <div class="activity-row">
                <strong>上午</strong><span>${escapeHtml(day.morning)}</span>
              </div>
              <div class="activity-row">
                <strong>下午</strong><span>${escapeHtml(day.afternoon)}</span>
              </div>
              <div class="activity-row">
                <strong>晚间</strong><span>${escapeHtml(day.evening)}</span>
              </div>
            </div>
            <div class="day-evidence">${evidence || '<span class="evidence-badge">未关联证据</span>'}</div>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelector("#panel-itinerary").innerHTML = `
    <div class="summary-banner">${escapeHtml(body.research?.summary || "暂无调研摘要")}</div>
    ${days || '<div class="review-card"><p>暂无逐日行程。</p></div>'}
  `;
}

function renderResearch(body) {
  const research = body.research || {};
  const routes = (research.route_decisions || [])
    .map(
      (route) => `
        <article class="route-card">
          <header>
            <h4>${escapeHtml(route.query)}</h4>
            <span class="type-badge">${escapeHtml(route.selected_source)}</span>
          </header>
          <p>${escapeHtml(route.route_reason)}</p>
          ${
            route.local_confidence == null
              ? ""
              : `<p>本地知识置信度：${escapeHtml(Number(route.local_confidence).toFixed(2))}</p>`
          }
        </article>
      `,
    )
    .join("");

  document.querySelector("#panel-research").innerHTML = `
    <section class="report-section">
      <h3>调研摘要</h3>
      <p>${escapeHtml(research.summary || "暂无")}</p>
    </section>
    <section class="report-section">
      <h3>相似案例洞察</h3>
      ${listMarkup(research.case_insights)}
    </section>
    <section class="report-section">
      <h3>旅行经验建议</h3>
      ${listMarkup(research.experience_advice)}
    </section>
    <section class="report-section">
      <h3>实时调研事实</h3>
      ${listMarkup(research.realtime_facts, "本次未调用实时检索")}
    </section>
    <section class="report-section">
      <h3>检索路由决策</h3>
      ${routes || "<p>暂无路由记录。</p>"}
    </section>
  `;
}

function renderEvidence(body) {
  const research = body.research || {};
  const evidence = (research.evidence || [])
    .map(
      (item) => `
        <article class="evidence-card">
          <header>
            <h4>${escapeHtml(item.evidence_id)} · ${escapeHtml(
              freshnessLabel[item.freshness] || item.freshness,
            )}</h4>
            <span class="type-badge">${escapeHtml(
              (item.source_ids || []).join(", "),
            )}</span>
          </header>
          <p>${escapeHtml(item.claim)}</p>
        </article>
      `,
    )
    .join("");

  const citations = (research.citations || [])
    .map((citation) => {
      const href = safeUrl(citation.url);
      const tag = href ? "a" : "div";
      const attributes = href
        ? `href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer"`
        : "";
      const score =
        citation.score == null
          ? ""
          : ` · 相关度 ${Math.round(Number(citation.score) * 100)}%`;
      return `
        <${tag} class="citation-link" ${attributes}>
          <div>
            <strong>${escapeHtml(citation.title)}</strong>
            <small>${escapeHtml(citation.source_id)}${escapeHtml(score)}</small>
          </div>
          <span class="type-badge">${escapeHtml(
            sourceLabel[citation.source_type] || citation.source_type,
          )}</span>
        </${tag}>
      `;
    })
    .join("");

  document.querySelector("#panel-evidence").innerHTML = `
    <section class="report-section">
      <h3>证据声明</h3>
      ${evidence || "<p>暂无结构化证据。</p>"}
    </section>
    <section class="report-section">
      <h3>引用来源</h3>
      <div class="citation-list">${citations || "<p>暂无引用来源。</p>"}</div>
    </section>
  `;
}

function renderReview(body) {
  const approved = Boolean(body.review?.approved);
  const validationPassed = Boolean(body.validation?.passed);
  const validationIssues = body.validation?.issues || [];
  const reviewIssues = body.review?.issues || [];
  const improvements = body.review?.improvement_instructions || [];

  document.querySelector("#panel-review").innerHTML = `
    <article class="review-card ${approved ? "is-approved" : "is-rejected"}">
      <div class="review-lead">
        <i>${approved ? "✓" : "!"}</i>
        <div>
          <strong>${approved ? "审核通过" : "需要修订"}</strong>
          <p>${escapeHtml(body.review?.summary || "暂无审核摘要")}</p>
        </div>
      </div>
    </article>
    <section class="report-section">
      <h3>规则校验 · ${validationPassed ? "PASS" : "FAIL"}</h3>
      ${
        validationIssues.length
          ? `<ul>${validationIssues
              .map(
                (issue) =>
                  `<li>[${escapeHtml(issue.code)}] ${escapeHtml(issue.message)}</li>`,
              )
              .join("")}</ul>`
          : "<p>未发现规则冲突。</p>"
      }
    </section>
    <section class="report-section">
      <h3>审核意见</h3>
      ${listMarkup(reviewIssues, "审核 Agent 未提出额外问题")}
    </section>
    <section class="report-section">
      <h3>改进指令</h3>
      ${listMarkup(improvements, "无需进一步修改")}
    </section>
    <section class="report-section">
      <h3>执行记录</h3>
      <p>工作流重试 ${escapeHtml(body.retry_count ?? 0)} 次${
        body.review?.requires_additional_research ? "，审核要求补充调研。" : "。"
      }</p>
    </section>
  `;
}

function renderEvidenceSummary(body) {
  const citations = body.research?.citations || [];
  const countByType = citations.reduce(
    (counts, citation) => {
      if (citation.source_type in counts) counts[citation.source_type] += 1;
      return counts;
    },
    { case: 0, experience: 0, realtime: 0 },
  );
  const passed = Boolean(body.validation?.passed);

  document.querySelector("#evidence-summary").innerHTML = `
    <h3>证据概览</h3>
    <div class="source-counts">
      <div><span>历史案例</span><strong>${countByType.case}</strong></div>
      <div><span>旅行经验</span><strong>${countByType.experience}</strong></div>
      <div><span>实时信息</span><strong>${countByType.realtime}</strong></div>
    </div>
    <div class="validation-card ${passed ? "" : "is-failed"}">
      <h4>规则校验</h4>
      <span>${passed ? "PASS" : "FAIL"}</span>
      <small>${passed ? "通过所有确定性检查" : "存在需要处理的规则问题"}</small>
    </div>
  `;
}

function renderResult(body, { savedPlanId = null } = {}) {
  latestPlanResponse = body;
  currentSavedPlanId = savedPlanId;
  renderItinerary(body);
  renderResearch(body);
  renderEvidence(body);
  renderReview(body);
  renderEvidenceSummary(body);

  metrics.destination.textContent = body.itinerary?.destination || "--";
  metrics.days.textContent = `${body.itinerary?.days || "--"} 天`;
  metrics.budget.textContent = formatCurrency(
    body.itinerary?.total_estimated_cost_cny,
  );
  metrics.citations.textContent = `${body.research?.citations?.length || 0} 条`;
  metrics.review.textContent = body.review?.approved ? "审核通过" : "需要修订";
  requestIdEl.textContent = body.research?.request_id || "任务已完成";
  requestIdEl.title = body.research?.request_id || "";
  savePlanButton.hidden = false;
  savePlanButton.disabled = Boolean(savedPlanId);
  savePlanButton.innerHTML = savedPlanId
    ? '<span aria-hidden="true">✓</span> 已保存'
    : '<span aria-hidden="true">＋</span> 保存到我的行程';
  downloadMarkdownButton.hidden = false;

  loadingEl.hidden = true;
  resultEl.hidden = false;
  setPipeline(5, "complete");
  activateTab("itinerary");
}

function showError(error) {
  latestPlanResponse = null;
  currentSavedPlanId = null;
  savePlanButton.hidden = true;
  downloadMarkdownButton.hidden = true;
  document.querySelector("#panel-itinerary").innerHTML = `
    <div class="error-card">
      <h3>本次规划未完成</h3>
      <p>${escapeHtml(error.message || "未知错误")}</p>
    </div>
  `;
  loadingEl.hidden = true;
  resultEl.hidden = false;
  document.querySelector("#evidence-summary").innerHTML = `
    <h3>运行说明</h3>
    <div class="review-card is-rejected">
      <p>系统没有切换到 Mock 或其他降级路径。详细错误已由后端记录，请结合日志定位。</p>
    </div>
  `;
  setPipeline(
    Math.max(
      0,
      pipelineSteps.findIndex((step) => step.classList.contains("is-active")),
    ),
    "error",
  );
  activateTab("itinerary");
}

async function loadSystemStatus() {
  const apiDot = document.querySelector("#api-dot");
  const apiState = document.querySelector("#api-state");
  try {
    const response = await fetch("/api/v1/ready", {
      headers: { Accept: "application/json" },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "服务未就绪");
    const total = Object.values(body.collections || {}).reduce(
      (sum, value) => sum + Number(value || 0),
      0,
    );
    document.querySelector("#knowledge-count").textContent = String(total);
    apiState.textContent = "API 正常";
    apiDot.classList.add("is-ok");
    formStatusDot.classList.add("is-ok");
  } catch {
    apiState.textContent = "API 未就绪";
    apiDot.classList.add("is-error");
    formStatusDot.classList.add("is-error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const payload = {
    destination: String(data.get("destination") || "").trim(),
    days: Number(data.get("days")),
    budget_cny: Number(data.get("budget")),
    travelers: splitValues(data.get("travelers")),
    interests: splitValues(data.get("interests")),
    pace: data.get("pace"),
    constraints: splitValues(data.get("constraints")),
  };

  latestPlanResponse = null;
  currentSavedPlanId = null;
  savePlanButton.hidden = true;
  downloadMarkdownButton.hidden = true;

  setIdleMetrics(payload);
  emptyEl.hidden = true;
  resultEl.hidden = true;
  loadingEl.hidden = false;
  requestIdEl.textContent = "任务执行中";
  submitButton.disabled = true;
  submitButton.setAttribute("aria-busy", "true");
  buttonLabel.textContent = "Agent 工作流执行中";
  statusEl.textContent = "调研 Agent 正在检索证据…";
  formStatusDot.classList.remove("is-error");
  formStatusDot.classList.add("is-ok");
  setPipeline(0);

  const stageTitles = [
    "正在检索历史案例与旅行经验",
    "调研 Agent 正在整合实时信息",
    "规划 Agent 正在生成逐日方案",
    "规则引擎正在检查预算与约束",
    "审核 Agent 正在完成最终复核",
  ];
  let stageIndex = 0;
  loadingTitleEl.textContent = stageTitles[stageIndex];
  const stageTimer = window.setInterval(() => {
    if (stageIndex >= stageTitles.length - 1) return;
    stageIndex += 1;
    setPipeline(stageIndex);
    loadingTitleEl.textContent = stageTitles[stageIndex];
    statusEl.textContent = `${stageTitles[stageIndex]}…`;
  }, 12000);

  try {
    const response = await fetch("/api/v1/plans", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "请求失败");

    renderResult(body);
    statusEl.textContent = `完成 · ${String(body.mode || "").toUpperCase()} 模式`;
  } catch (error) {
    showError(error);
    statusEl.textContent = "失败，未执行模式降级；请查看日志。";
    formStatusDot.classList.remove("is-ok");
    formStatusDot.classList.add("is-error");
  } finally {
    window.clearInterval(stageTimer);
    submitButton.disabled = false;
    submitButton.removeAttribute("aria-busy");
    buttonLabel.textContent = "开始调研与规划";
  }
});

savePlanButton.addEventListener("click", async () => {
  if (!latestPlanResponse || currentSavedPlanId) return;
  const originalLabel = savePlanButton.innerHTML;
  savePlanButton.disabled = true;
  savePlanButton.textContent = "正在保存…";
  try {
    const response = await fetch("/api/v1/saved-plans", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(latestPlanResponse),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(body, "行程保存失败"));
    currentSavedPlanId = body.item.plan_id;
    savePlanButton.innerHTML = '<span aria-hidden="true">✓</span> 已保存';
    statusEl.textContent = body.created
      ? "行程已保存到我的行程。"
      : "该行程之前已经保存。";
  } catch (error) {
    savePlanButton.disabled = false;
    savePlanButton.innerHTML = originalLabel;
    statusEl.textContent = error.message;
    formStatusDot.classList.remove("is-ok");
    formStatusDot.classList.add("is-error");
  }
});

async function downloadMarkdownResponse(response, fallbackName) {
  if (!response.ok) {
    const body = await response.json();
    throw new Error(apiErrorMessage(body, "Markdown 生成失败"));
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const filename = encodedName ? decodeURIComponent(encodedName) : fallbackName;
  const blobUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
  return filename;
}

downloadMarkdownButton.addEventListener("click", async () => {
  if (!latestPlanResponse) return;
  const originalLabel = downloadMarkdownButton.innerHTML;
  downloadMarkdownButton.disabled = true;
  downloadMarkdownButton.textContent = "正在生成…";
  try {
    const response = await fetch("/api/v1/plans/export/markdown", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/markdown" },
      body: JSON.stringify(latestPlanResponse),
    });
    const filename = await downloadMarkdownResponse(
      response,
      `${latestPlanResponse.itinerary?.destination || "旅行"}-行程方案.md`,
    );
    statusEl.textContent = `已生成 ${filename}`;
  } catch (error) {
    statusEl.textContent = error.message;
    formStatusDot.classList.remove("is-ok");
    formStatusDot.classList.add("is-error");
  } finally {
    downloadMarkdownButton.disabled = false;
    downloadMarkdownButton.innerHTML = originalLabel;
  }
});

const knowledgeDialog = document.querySelector("#knowledge-dialog");
const knowledgeSearchForm = document.querySelector("#knowledge-search-form");
const knowledgeCreateForm = document.querySelector("#knowledge-create-form");
const knowledgeList = document.querySelector("#knowledge-list");
const knowledgeCreateKind = document.querySelector("#knowledge-create-kind");
const knowledgeCaseFields = document.querySelector("#knowledge-case-fields");
const knowledgeExperienceFields = document.querySelector(
  "#knowledge-experience-fields",
);
const knowledgeState = { offset: 0, limit: 10, total: 0 };

const knowledgeKindLabel = {
  cases: "历史案例",
  experiences: "旅行经验",
};

function apiErrorMessage(body, fallback) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((item) => item.msg || "字段校验失败").join("；");
  }
  return fallback;
}

function knowledgeMetadataMarkup(metadata = {}) {
  const hiddenKeys = new Set(["title"]);
  return Object.entries(metadata)
    .filter(([key, value]) => !hiddenKeys.has(key) && value !== "" && value != null)
    .map(
      ([key, value]) =>
        `<span><b>${escapeHtml(key)}</b>${escapeHtml(value)}</span>`,
    )
    .join("");
}

function renderKnowledgeList(items = []) {
  if (!items.length) {
    knowledgeList.innerHTML = `
      <div class="knowledge-empty">
        <strong>没有找到匹配知识</strong>
        <p>可以清空目的地或更换关键词后重新查询。</p>
      </div>
    `;
    return;
  }
  knowledgeList.innerHTML = items
    .map(
      (item) => `
        <article class="knowledge-record">
          <header>
            <div>
              <span class="knowledge-kind-badge">${escapeHtml(
                knowledgeKindLabel[item.kind] || item.kind,
              )}</span>
              <h4>${escapeHtml(item.title)}</h4>
            </div>
            <code>${escapeHtml(item.id)}</code>
          </header>
          <p>${escapeHtml(item.text)}</p>
          <div class="knowledge-metadata">${knowledgeMetadataMarkup(item.metadata)}</div>
        </article>
      `,
    )
    .join("");
}

function updateKnowledgePagination() {
  const page = Math.floor(knowledgeState.offset / knowledgeState.limit) + 1;
  const pages = Math.max(1, Math.ceil(knowledgeState.total / knowledgeState.limit));
  document.querySelector("#knowledge-page").textContent = `第 ${page} / ${pages} 页`;
  document.querySelector("#knowledge-prev").disabled = knowledgeState.offset === 0;
  document.querySelector("#knowledge-next").disabled =
    knowledgeState.offset + knowledgeState.limit >= knowledgeState.total;
}

async function loadKnowledge() {
  const data = new FormData(knowledgeSearchForm);
  const params = new URLSearchParams({
    kind: String(data.get("kind") || "all"),
    offset: String(knowledgeState.offset),
    limit: String(knowledgeState.limit),
  });
  const destination = String(data.get("destination") || "").trim();
  const query = String(data.get("query") || "").trim();
  if (destination) params.set("destination", destination);
  if (query) params.set("query", query);

  knowledgeList.innerHTML = '<div class="knowledge-loading">正在读取当前向量库…</div>';
  try {
    const response = await fetch(`/api/v1/knowledge?${params}`, {
      headers: { Accept: "application/json" },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(body, "知识库读取失败"));
    knowledgeState.total = Number(body.total || 0);
    document.querySelector("#knowledge-result-count").textContent =
      `${knowledgeState.total} 条`;
    renderKnowledgeList(body.items);
  } catch (error) {
    knowledgeState.total = 0;
    knowledgeList.innerHTML = `
      <div class="knowledge-empty is-error">
        <strong>读取失败</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  } finally {
    updateKnowledgePagination();
  }
}

function toggleKnowledgeKindFields() {
  const isCase = knowledgeCreateKind.value === "cases";
  knowledgeCaseFields.hidden = !isCase;
  knowledgeExperienceFields.hidden = isCase;
  knowledgeCaseFields.querySelectorAll("input, select").forEach((field) => {
    field.disabled = !isCase;
  });
  knowledgeExperienceFields.querySelectorAll("input, select").forEach((field) => {
    field.disabled = isCase;
  });
}

document.querySelector("#knowledge-open").addEventListener("click", () => {
  knowledgeDialog.showModal();
  knowledgeState.offset = 0;
  loadKnowledge();
});

document.querySelector("#knowledge-close").addEventListener("click", () => {
  knowledgeDialog.close();
});

knowledgeSearchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  knowledgeState.offset = 0;
  loadKnowledge();
});

document.querySelector("#knowledge-prev").addEventListener("click", () => {
  knowledgeState.offset = Math.max(0, knowledgeState.offset - knowledgeState.limit);
  loadKnowledge();
});

document.querySelector("#knowledge-next").addEventListener("click", () => {
  if (knowledgeState.offset + knowledgeState.limit >= knowledgeState.total) return;
  knowledgeState.offset += knowledgeState.limit;
  loadKnowledge();
});

knowledgeCreateKind.addEventListener("change", toggleKnowledgeKindFields);

knowledgeCreateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(knowledgeCreateForm);
  const kind = String(data.get("kind"));
  const payload = {
    kind,
    title: String(data.get("title") || "").trim(),
    text: String(data.get("text") || "").trim(),
    destination: String(data.get("destination") || "").trim(),
    traveler_tags: splitValues(data.get("traveler_tags")),
    interest_tags: splitValues(data.get("interest_tags")),
    quality_score: Number(data.get("quality_score") || 0.8),
  };
  const recordId = String(data.get("record_id") || "").trim();
  if (recordId) payload.record_id = recordId;
  if (kind === "cases") {
    payload.days = Number(data.get("days"));
    payload.pace = data.get("pace");
    payload.budget_level = data.get("budget_level");
  } else {
    payload.scene = String(data.get("scene") || "").trim();
    payload.freshness = data.get("freshness");
  }

  const button = document.querySelector("#knowledge-create-button");
  const createStatus = document.querySelector("#knowledge-create-status");
  button.disabled = true;
  createStatus.className = "knowledge-create-status";
  createStatus.textContent = "正在保存源数据并生成向量…";
  try {
    const response = await fetch("/api/v1/knowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(body, "新增失败"));
    createStatus.classList.add("is-success");
    createStatus.textContent = `已写入：${body.record.id}。源数据和当前索引均已更新。`;
    knowledgeCreateForm.reset();
    toggleKnowledgeKindFields();
    knowledgeState.offset = 0;
    await Promise.all([loadKnowledge(), loadSystemStatus()]);
  } catch (error) {
    createStatus.classList.add("is-error");
    createStatus.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

const savedPlansDialog = document.querySelector("#saved-plans-dialog");
const savedPlansSearchForm = document.querySelector("#saved-plans-search-form");
const savedPlansList = document.querySelector("#saved-plans-list");
const savedPlansState = { offset: 0, limit: 8, total: 0 };

function formatSavedDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderSavedPlans(items = []) {
  if (!items.length) {
    savedPlansList.innerHTML = `
      <div class="knowledge-empty">
        <strong>暂时没有匹配的行程</strong>
        <p>完成一次规划后，点击“保存到我的行程”即可在这里长期查看。</p>
      </div>
    `;
    return;
  }
  savedPlansList.innerHTML = items
    .map(
      (item) => `
        <article class="saved-plan-card">
          <div class="saved-plan-main">
            <span class="saved-plan-destination">${escapeHtml(item.destination)}</span>
            <h3>${escapeHtml(item.title)}</h3>
            <div class="saved-plan-meta">
              <span>${escapeHtml(item.days)} 天</span>
              <span>版本 ${escapeHtml(item.version)}</span>
              <span>更新于 ${escapeHtml(formatSavedDate(item.updated_at))}</span>
            </div>
          </div>
          <div class="saved-plan-actions">
            <button type="button" data-action="open" data-plan-id="${escapeHtml(item.plan_id)}">
              打开行程
            </button>
            <button type="button" class="is-secondary" data-action="download" data-plan-id="${escapeHtml(item.plan_id)}">
              下载 MD
            </button>
          </div>
        </article>
      `,
    )
    .join("");
}

function updateSavedPlansPagination() {
  const page = Math.floor(savedPlansState.offset / savedPlansState.limit) + 1;
  const pages = Math.max(1, Math.ceil(savedPlansState.total / savedPlansState.limit));
  document.querySelector("#saved-plans-page").textContent = `第 ${page} / ${pages} 页`;
  document.querySelector("#saved-plans-prev").disabled = savedPlansState.offset === 0;
  document.querySelector("#saved-plans-next").disabled =
    savedPlansState.offset + savedPlansState.limit >= savedPlansState.total;
}

async function loadSavedPlans() {
  const data = new FormData(savedPlansSearchForm);
  const params = new URLSearchParams({
    offset: String(savedPlansState.offset),
    limit: String(savedPlansState.limit),
  });
  const destination = String(data.get("destination") || "").trim();
  const query = String(data.get("query") || "").trim();
  if (destination) params.set("destination", destination);
  if (query) params.set("query", query);

  savedPlansList.innerHTML = '<div class="knowledge-loading">正在读取已保存行程…</div>';
  try {
    const response = await fetch(`/api/v1/saved-plans?${params}`, {
      headers: { Accept: "application/json" },
    });
    const body = await response.json();
    if (!response.ok) throw new Error(apiErrorMessage(body, "行程库读取失败"));
    savedPlansState.total = Number(body.total || 0);
    document.querySelector("#saved-plans-count").textContent =
      `${savedPlansState.total} 条`;
    renderSavedPlans(body.items);
  } catch (error) {
    savedPlansState.total = 0;
    savedPlansList.innerHTML = `
      <div class="knowledge-empty is-error">
        <strong>读取失败</strong>
        <p>${escapeHtml(error.message)}</p>
      </div>
    `;
  } finally {
    updateSavedPlansPagination();
  }
}

document.querySelector("#saved-plans-open").addEventListener("click", () => {
  savedPlansDialog.showModal();
  savedPlansState.offset = 0;
  loadSavedPlans();
});

document.querySelector("#saved-plans-close").addEventListener("click", () => {
  savedPlansDialog.close();
});

savedPlansSearchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  savedPlansState.offset = 0;
  loadSavedPlans();
});

document.querySelector("#saved-plans-prev").addEventListener("click", () => {
  savedPlansState.offset = Math.max(0, savedPlansState.offset - savedPlansState.limit);
  loadSavedPlans();
});

document.querySelector("#saved-plans-next").addEventListener("click", () => {
  if (savedPlansState.offset + savedPlansState.limit >= savedPlansState.total) return;
  savedPlansState.offset += savedPlansState.limit;
  loadSavedPlans();
});

savedPlansList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action][data-plan-id]");
  if (!button) return;
  const planId = button.dataset.planId;
  const action = button.dataset.action;
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = action === "open" ? "正在打开…" : "正在生成…";
  try {
    if (action === "open") {
      const response = await fetch(`/api/v1/saved-plans/${encodeURIComponent(planId)}`, {
        headers: { Accept: "application/json" },
      });
      const body = await response.json();
      if (!response.ok) throw new Error(apiErrorMessage(body, "行程读取失败"));
      renderResult(body.plan, { savedPlanId: planId });
      savedPlansDialog.close();
      statusEl.textContent = `已打开保存的行程 · 版本 ${body.version}`;
      formStatusDot.classList.remove("is-error");
      formStatusDot.classList.add("is-ok");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    const response = await fetch(
      `/api/v1/saved-plans/${encodeURIComponent(planId)}/export/markdown`,
      { method: "POST", headers: { Accept: "text/markdown" } },
    );
    const filename = await downloadMarkdownResponse(response, "旅行-行程方案.md");
    statusEl.textContent = `已生成 ${filename}`;
  } catch (error) {
    statusEl.textContent = error.message;
    formStatusDot.classList.remove("is-ok");
    formStatusDot.classList.add("is-error");
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
});

toggleKnowledgeKindFields();

setPipeline(-1);
loadSystemStatus();
