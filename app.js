const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
let cache = [];
let baseStatusFilter = "open";
let activeJobId = null;
let radarMode = localStorage.getItem("alfred-radar-mode") || "cards";
let quickFilter = null;
let pendingDeleteEditalId = null;
let pipelineCache = [];
let draggedPipelineId = null;
let activeChecklistEditalId = null;
let checklistCache = [];
let monitorJobId = null;
let savedReportsCache = [];
let usersCache = [];
let assignableUsersCache = [];
let notificationConfigCache = null;
const selectedEditais = new Set();
const accessPermissions = new Set(JSON.parse(document.body.dataset.permissions || "[]"));
const isAdministrator = document.body.dataset.isAdmin === "true";
const landingView = document.body.dataset.landingView || "dashboard";
const currentUserName = document.body.dataset.currentUserName || "Usuário";
const viewPermissionMap = {dashboard:"dashboard",base:"base_editais",radar:"radar",analysis:"consultor",pipeline:"pipeline",monitoring:"monitoramento",reports:"relatorios",upload:"docs",history:"historico",users:"__admin__",notifications:"__admin__",settings:"__admin__"};
const hasAccess = permission => isAdministrator || accessPermissions.has(permission);
const canOpenView = view => ["users","notifications","settings"].includes(view) ? isAdministrator : hasAccess(viewPermissionMap[view] || "dashboard");
const brazilianStates = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"];
const pipelineStages = [
  ["nova_oportunidade", "Nova oportunidade"],
  ["triagem", "Triagem"],
  ["em_analise", "Em análise"],
  ["decisao_participacao", "Decisão de participação"],
  ["documentacao", "Documentação"],
  ["proposta_enviada", "Proposta enviada"],
  ["ganha", "Ganha"],
  ["perdida_arquivada", "Perdida / Arquivada"]
];
const pipelineStageLabels = Object.fromEntries(pipelineStages);
const pipelinePriorityLabels = {baixa:"Baixa", normal:"Normal", alta:"Alta", critica:"Crítica"};
const favorites = new Set(JSON.parse(localStorage.getItem("alfred-favorites") || "[]"));

const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

async function api(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(url, {...options, headers});
  if (response.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new Error("Sua sessão expirou. Entre novamente.");
  }
  if (!response.ok) {
    let data = {};
    try { data = await response.json(); } catch {}
    throw new Error(data.detail || `Erro ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}
async function downloadPdf(url, payload, fallbackName = "Relatorio_HORUS_CONNECTIVE.pdf") {
  const headers = new Headers({"Content-Type":"application/json"});
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(url, {method:"POST", headers, body:JSON.stringify(payload)});
  if (!response.ok) {
    let data = {};
    try { data = await response.json(); } catch {}
    throw new Error(data.detail || `Erro ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  const filename = match ? decodeURIComponent(match[1].replace(/"/g, "")) : fallbackName;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

const money = (value, short = false) => value == null ? "Não informado" : new Intl.NumberFormat("pt-BR", {style:"currency", currency:"BRL", notation:short ? "compact" : "standard", maximumFractionDigits:short ? 1 : 2}).format(value);
const dateFmt = (value, full = true) => !value ? "Não informado" : new Intl.DateTimeFormat("pt-BR", full ? {dateStyle:"short", timeStyle:"short"} : {dateStyle:"short"}).format(new Date(value));
const iso = date => date.toISOString().slice(0, 10);
const daysUntil = value => value ? Math.ceil((new Date(value) - new Date()) / 864e5) : null;
function setStatus(box, message, type = "") { box.className = `status-box ${type}`; box.textContent = message; }
function toast(message) { const el = document.createElement("div"); el.className = "toast"; el.textContent = message; $("toastRegion").append(el); setTimeout(() => el.remove(), 2600); }

const titles = {dashboard:"Mission Control", radar:"Radar de Licitações", pipeline:"Hórus Pipeline", monitoring:"Monitoramento Diário", reports:"Relatórios salvos", base:"Base de editais", analysis:"Consultor Hórus", favorites:"Prioridades", history:"Histórico", upload:"Hórus Docs", users:"Usuários e permissões",notifications:"Notificações diárias",settings:"Configurações de busca"};
function switchView(name) {
  if (!canOpenView(name)) { toast("Seu usuário não possui permissão para este módulo."); return; }
  document.querySelectorAll(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  document.querySelectorAll(".nav-item").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  $("pageTitle").textContent = titles[name] || "Hórus Connective";
  $("sidebar").classList.remove("open");
  if (name === "favorites") renderFavorites();
  if (name === "pipeline") loadPipeline();
  if (name === "monitoring") loadMonitorConfig();
  if (name === "reports") loadSavedReports();
  if (name === "users" && isAdministrator) loadUsers();
  if (name === "notifications" && isAdministrator) loadNotificationConfig();
  if (name === "settings" && isAdministrator) loadSegmentSettings();
}

document.addEventListener("click", event => {
  const nav = event.target.closest("[data-view]");
  if (nav) switchView(nav.dataset.view);
  const go = event.target.closest("[data-goto]");
  if (go) switchView(go.dataset.goto);
});

function opportunityScore(edital) {
  let score = 35;
  const text = `${edital.title || ""} ${edital.object_text || ""}`.toLowerCase();
  const matches = ["publicidade","propaganda","comunicação","marketing","mídia","campanha","agência","planejamento"].filter(word => text.includes(word));
  score += Math.min(matches.length * 7, 35);
  if ((edital.estimated_value || 0) >= 1000000) score += 8;
  const days = daysUntil(edital.proposal_end);
  if (days !== null && days > 5 && days < 45) score += 7;
  if (edital.indexing_status === "indexed" || edital.indexing_status === "completed") score += 5;
  return Math.min(99, score);
}
function scoreClass(score) { return score >= 75 ? "high" : score >= 55 ? "medium" : "low"; }
function scoreLabel(score) { return score >= 75 ? "Alta aderência" : score >= 55 ? "Aderência moderada" : "Revisar aderência"; }
function deadlineText(value) {
  const days = daysUntil(value);
  if (days === null) return {text:"Prazo não informado", urgent:false};
  if (days < 0) return {text:"Encerrado", urgent:true};
  if (days === 0) return {text:"Encerra hoje", urgent:true};
  if (days <= 7) return {text:`${days} dia(s)`, urgent:true};
  return {text:`${days} dias`, urgent:false};
}
function saveFavorites() {
  localStorage.setItem("alfred-favorites", JSON.stringify([...favorites]));
  updateFavoriteCounters();
}
function updateFavoriteCounters() {
  if ($("favoritesBadge")) $("favoritesBadge").textContent = favorites.size;
  if ($("favoriteInsight")) $("favoriteInsight").textContent = favorites.size;
}

function radarCard(edital) {
  const score = opportunityScore(edital);
  const deadline = deadlineText(edital.proposal_end);
  return `<article class="radar-card" data-open-edital="${esc(edital.id)}">
    <div class="radar-card-top"><div><span class="status-pill">${esc(edital.uf || "BR")}</span> <span class="score-pill ${scoreClass(score)}">${score}%</span></div><span class="deadline ${deadline.urgent ? "urgent" : ""}">${esc(deadline.text)}</span></div>
    <h3>${esc(edital.title)}</h3>
    <p><strong>${esc(edital.organization || "Órgão não informado")}</strong> · ${esc(edital.modality_name || edital.source)}</p>
    <p class="object">${esc((edital.object_text || "Sem descrição").slice(0, 240))}</p>
    <div class="radar-card-actions"><strong>${esc(money(edital.estimated_value, true))}</strong><div><button class="ghost compact" data-open-pipeline="${esc(edital.id)}">Pipeline</button><button class="favorite-button ${favorites.has(edital.id) ? "active" : ""}" data-favorite="${esc(edital.id)}">★ ${favorites.has(edital.id) ? "Favorito" : "Favoritar"}</button></div></div>
  </article>`;
}

function sortedAndFiltered(items) {
  let result = [...items];
  if (quickFilter === "high") result = result.filter(item => opportunityScore(item) >= 75);
  if (quickFilter === "urgent") result = result.filter(item => { const days = daysUntil(item.proposal_end); return days !== null && days >= 0 && days <= 7; });
  if (quickFilter === "million") result = result.filter(item => (item.estimated_value || 0) >= 1000000);
  if (quickFilter === "favorites") result = result.filter(item => favorites.has(item.id));
  const sort = $("radarSort")?.value || "deadline";
  if (sort === "score") result.sort((a,b) => opportunityScore(b) - opportunityScore(a));
  if (sort === "value") result.sort((a,b) => (b.estimated_value || 0) - (a.estimated_value || 0));
  if (sort === "deadline") result.sort((a,b) => new Date(a.proposal_end || "2999-01-01") - new Date(b.proposal_end || "2999-01-01"));
  return result;
}
function renderRadar(items = cache) {
  const result = sortedAndFiltered(items);
  $("radarList").className = `radar-list ${radarMode}`;
  $("radarList").innerHTML = result.length ? result.map(radarCard).join("") : "<p class='hint'>Nenhuma oportunidade encontrada.</p>";
  $("radarResultTitle").textContent = `${result.length} oportunidade(s)`;
}
function renderFavorites() {
  const items = cache.filter(item => favorites.has(item.id));
  $("favoritesList").innerHTML = items.length ? items.map(radarCard).join("") : "<p class='hint'>Nenhuma oportunidade foi favoritada.</p>";
}
function editalCard(edital) {
  const selected = selectedEditais.has(edital.id) ? "checked" : "";
  const progress = Number(edital.checklist_progress || 0);
  const checklistLabel = edital.checklist_total ? `${edital.checklist_completed}/${edital.checklist_total}` : "Gerar";
  return `<article class="edital-item" data-edital-id="${esc(edital.id)}" data-open-edital="${esc(edital.id)}" tabindex="0" role="button" aria-label="Abrir detalhes de ${esc(edital.title)}">
    <div class="edital-select">
      <input class="edital-checkbox" type="checkbox" value="${esc(edital.id)}" ${selected} aria-label="Selecionar ${esc(edital.title)}">
    </div>
    <div class="edital-content">
      <div class="edital-title-row"><p class="edital-title">${esc(edital.title)}</p><span class="checklist-mini-badge" style="--mini-progress:${progress}%">Checklist ${esc(checklistLabel)}</span></div>
      <p class="edital-meta">${esc(edital.organization || "Órgão não informado")} · ${esc(edital.uf || "BR")} · ${esc(edital.modality_name || edital.source)}</p>
      <p class="edital-meta">Encerramento: ${esc(dateFmt(edital.proposal_end))} · ${esc(money(edital.estimated_value))}</p>
      <p class="edital-object">${esc((edital.object_text || "Sem descrição").slice(0, 360))}</p>
    </div>
    <div class="edital-actions" aria-label="Ações do edital">
      <button class="edital-action detail-action" type="button" data-open-edital="${esc(edital.id)}" title="Abrir detalhes"><span aria-hidden="true">◉</span> Detalhes</button><button class="edital-action checklist-action" type="button" data-open-checklist="${esc(edital.id)}" title="Abrir checklist"><span aria-hidden="true">✓</span> Checklist</button>
      <button class="edital-action edit-action" type="button" data-edit-edital="${esc(edital.id)}" title="Editar edital"><span aria-hidden="true">✎</span> Editar</button>
      <button class="edital-action delete-action" type="button" data-delete-edital="${esc(edital.id)}" title="Excluir edital"><span aria-hidden="true">⌫</span> Excluir</button>
    </div>
  </article>`;
}
function selection(event) {
  if (event?.target?.classList?.contains("edital-checkbox")) {
    event.target.checked ? selectedEditais.add(event.target.value) : selectedEditais.delete(event.target.value);
  }
  const count = selectedEditais.size;
  $("selectionCount").textContent = count ? `${count} edital(is) selecionado(s)` : "Consulta em toda a base";
  if ($("baseSelectionCount")) $("baseSelectionCount").textContent = `${count} selecionado${count === 1 ? "" : "s"}`;
  if ($("generateSelectedReportButton")) $("generateSelectedReportButton").disabled = count === 0;
  if ($("deleteSelectedButton")) $("deleteSelectedButton").disabled = count === 0;
}


function populateUfs(items = []) {
  const select = $("radarUf");
  if (!select) return;
  const current = select.value;
  const discovered = items.map(item => String(item.uf || "").trim().toUpperCase()).filter(Boolean);
  const states = [...new Set([...brazilianStates, ...discovered])].sort();
  select.innerHTML = '<option value="">Todos os estados</option>' + states.map(uf => `<option value="${esc(uf)}">${esc(uf)}</option>`).join("");
  select.value = states.includes(current) ? current : "";
}
async function bulkDeleteEditais({ids = [], deleteClosed = false} = {}) {
  const label = deleteClosed ? "todos os editais encerrados" : `${ids.length} edital(is) selecionado(s)`;
  if (!window.confirm(`Excluir definitivamente ${label}? Os documentos e checklists vinculados também serão removidos.`)) return;
  try {
    const result = await api("/api/editais/bulk-delete", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({edital_ids:ids, delete_closed:deleteClosed})});
    selectedEditais.clear();
    selection();
    toast(`${result.deleted || 0} edital(is) excluído(s).`);
    await Promise.all([loadEditais(), dashboard(), history()]);
  } catch (error) {
    toast(error.message || "Não foi possível excluir os editais.");
  }
}

async function loadEditais() {
  const query = $("editaisSearch").value.trim();
  try {
    cache = await api(`/api/editais?limit=200&q=${encodeURIComponent(query)}&situacao=${encodeURIComponent(baseStatusFilter)}`);
    $("editaisList").innerHTML = cache.length ? cache.map(editalCard).join("") : "<p class='hint'>Nenhum edital encontrado.</p>";
    document.querySelectorAll(".edital-checkbox").forEach(check => check.onchange = selection); selection();
    renderRadar(); renderRecent(cache.slice(0, 6)); renderFavorites(); populateUfs(cache); updateFavoriteCounters(); updateExecutiveAdvisor();
  } catch (error) { $("editaisList").innerHTML = `<p class='hint'>${esc(error.message)}</p>`; }
}
async function applyFilters() {
  const params = new URLSearchParams({limit:"200"});
  if ($("radarSearch").value) params.set("q", $("radarSearch").value);
  if ($("radarUf").value) params.set("uf", $("radarUf").value);
  if ($("radarModality").value) params.set("modalidade", $("radarModality").value);
  if ($("radarStatus").value) params.set("situacao", $("radarStatus").value);
  if ($("radarSource")?.value) params.set("fonte", $("radarSource").value);
  cache = await api(`/api/editais?${params}`);
  renderRadar(); renderFavorites();
}
function clearFilters() {
  $("radarSearch").value = ""; $("radarUf").value = ""; $("radarModality").value = ""; $("radarStatus").value = "open"; if ($("radarSource")) $("radarSource").value = "";
  quickFilter = null; document.querySelectorAll("[data-quick]").forEach(button => button.classList.remove("active")); applyFilters();
}
function renderRecent(items) {
  $("recentOpportunities").innerHTML = items.length ? items.map(item => `<div class="opportunity-row" data-open-edital="${esc(item.id)}"><div><strong>${esc(item.title)}</strong><small>${esc(item.organization || "Órgão não informado")}</small></div><span>${esc(pipelineStageLabels[item.pipeline_stage] || item.modality_name || item.source)}</span><span>${esc(item.uf || "BR")}</span><strong>${esc(money(item.estimated_value, true))}</strong></div>`).join("") : "<p class='hint'>Sem dados.</p>";
}
function updateExecutiveAdvisor() {
  const greetingHour = new Date().getHours();
  const greeting = greetingHour < 12 ? "Bom dia" : greetingHour < 18 ? "Boa tarde" : "Boa noite";
  if ($("alfredGreeting")) $("alfredGreeting").textContent = `${greeting}, ${currentUserName.split(" ")[0]}.`;
  if (!cache.length) return;
  const advisorItems = cache.filter(item => !["ganha", "perdida_arquivada"].includes(item.pipeline_stage));
  const ranked = [...(advisorItems.length ? advisorItems : cache)].sort((a, b) => {
    const scoreDelta = opportunityScore(b) - opportunityScore(a);
    if (scoreDelta) return scoreDelta;
    return (b.estimated_value || 0) - (a.estimated_value || 0);
  });
  const best = ranked[0];
  const score = opportunityScore(best);
  const deadline = deadlineText(best.proposal_end);
  $("advisorTitle").textContent = best.title;
  $("advisorScore").textContent = `${score}%`;
  $("advisorText").textContent = `${best.organization || "Órgão não informado"} · ${best.uf || "BR"} · Recomendo revisar o objeto e iniciar a análise documental.`;
  if ($("advisorValue")) $("advisorValue").textContent = money(best.estimated_value, true);
  if ($("advisorDeadline")) $("advisorDeadline").textContent = dateFmt(best.proposal_end, false);
}

function relativeTime(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "agora";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

async function dashboard() {
  const data = await api("/api/dashboard");
  $("kpiOpen").textContent = data.pipeline_new.toLocaleString("pt-BR");
  $("navOpenBadge").textContent = data.open_opportunities;
  $("kpiTotal").textContent = data.pipeline_analysis.toLocaleString("pt-BR");
  $("kpiIndexed").textContent = data.pipeline_proposals.toLocaleString("pt-BR");
  if ($("kpiWins")) $("kpiWins").textContent = data.pipeline_wins.toLocaleString("pt-BR");
  $("kpiIndexRate").textContent = `${data.indexing_rate}%`;
  $("kpiValue").textContent = money(data.pipeline_mapped_value, true);
  $("kpiAverage").textContent = `Ticket médio ${money(data.average_value_open, true)}`;
  $("kpiClosing").textContent = `${data.closing_7_days} encerram em 7 dias`;
  $("urgentInsight").textContent = data.closing_7_days;
  $("monthInsight").textContent = data.closing_30_days;
  if ($("pipelineBadge")) $("pipelineBadge").textContent = data.pipeline_active;
  $("heroSummary").textContent = `${data.pipeline_new} oportunidades novas, ${data.pipeline_analysis} em análise e ${data.pipeline_proposals} proposta(s) enviada(s).`;
  const healthScore = Math.max(0, Math.min(100, Math.round(data.indexing_rate * .5 + Math.min(data.pipeline_active * 3, 50))));
  $("healthScore").textContent = `${healthScore}%`; $("healthScoreRing").style.setProperty("--health", `${healthScore}%`);
  $("healthScoreLabel").textContent = healthScore >= 80 ? "Saudável" : healthScore >= 60 ? "Atenção" : "Em preparação";
  $("healthHeadline").textContent = healthScore >= 80 ? "Operação bem posicionada" : healthScore >= 60 ? "Operação estável, com pontos de atenção" : "Base em fase de consolidação";
  $("healthDescription").textContent = `${data.indexed_editais} editais indexados e ${data.pipeline_active} oportunidade(s) ativas no pipeline.`;
  const maxState = Math.max(...data.states.map(item => item.count), 1);
  $("stateRadar").innerHTML = data.states.map(item => `<button class="state-cell ${item.count >= maxState * .55 ? "hot" : ""}" data-state="${esc(item.uf)}"><strong>${esc(item.uf)}</strong><span>${item.count}</span></button>`).join("");
  const maxModality = Math.max(...data.modalities.map(item => item.count), 1);
  $("modalityChart").innerHTML = data.modalities.map(item => `<div class="bar-row"><div class="bar-label"><span>${esc(item.name)}</span><strong>${item.count}</strong></div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(8, item.count / maxModality * 100)}%"></div></div></div>`).join("");
  $("organizationList").innerHTML = data.organizations.map((item, index) => `<div class="rank-item"><span>${index + 1}. ${esc(item.name)}</span><strong>${item.count}</strong></div>`).join("");
  if ($("activityList")) {
    $("activityList").innerHTML = data.pipeline_activity.length ? data.pipeline_activity.map(event => `<div data-open-pipeline="${esc(event.edital_id)}"><span class="feed-icon">${event.event_type === "stage_changed" ? "↗" : "✎"}</span><p><strong>${esc(event.description)}</strong><small>${esc(event.edital_title)}${event.organization ? ` · ${esc(event.organization)}` : ""}</small></p><time>${esc(relativeTime(event.created_at))}</time></div>`).join("") : `<div><span class="feed-icon">◉</span><p><strong>Pipeline pronto</strong><small>Mova uma oportunidade para registrar a primeira atividade.</small></p><time>agora</time></div>`;
  }
}

function pipelineCard(item) {
  const deadline = deadlineText(item.proposal_end);
  const priority = item.pipeline_priority || "normal";
  const stageOptions = pipelineStages.map(([key, label]) => `<option value="${key}" ${key === item.pipeline_stage ? "selected" : ""}>${esc(label)}</option>`).join("");
  return `<article class="pipeline-card" draggable="true" data-pipeline-card="${esc(item.id)}">
    <div class="pipeline-card-top"><span class="pipeline-priority priority-${esc(priority)}">${esc(pipelinePriorityLabels[priority] || "Normal")}</span><span class="deadline ${deadline.urgent ? "urgent" : ""}">${esc(deadline.text)}</span></div>
    <h4>${esc(item.title)}</h4><p class="pipeline-org">${esc(item.organization || "Órgão não informado")} · ${esc(item.uf || "BR")}</p>
    <div class="pipeline-card-value"><strong>${esc(money(item.estimated_value, true))}</strong><small>${esc(item.pipeline_responsible || "Sem responsável")}</small></div>
    <div class="pipeline-checklist-progress"><span style="width:${Number(item.checklist_progress || 0)}%"></span><small>Checklist ${Number(item.checklist_progress || 0)}%</small></div>
    <div class="pipeline-card-actions"><select data-pipeline-stage-select="${esc(item.id)}" aria-label="Mover etapa">${stageOptions}</select><button class="ghost" type="button" data-open-checklist="${esc(item.id)}">Checklist</button><button class="ghost" type="button" data-open-pipeline="${esc(item.id)}">Detalhes</button></div>
  </article>`;
}
function pipelineSummary(items) {
  const count = stage => items.filter(item => item.pipeline_stage === stage).length;
  const analysis = items.filter(item => ["triagem","em_analise","decisao_participacao","documentacao"].includes(item.pipeline_stage)).length;
  const active = items.filter(item => !["ganha", "perdida_arquivada"].includes(item.pipeline_stage));
  $("pipelineNewCount").textContent = count("nova_oportunidade");
  $("pipelineAnalysisCount").textContent = analysis;
  $("pipelineProposalCount").textContent = count("proposta_enviada");
  $("pipelineWinCount").textContent = count("ganha");
  $("pipelineMappedValue").textContent = money(active.reduce((sum, item) => sum + Number(item.estimated_value || 0), 0), true);
  if ($("pipelineBadge")) $("pipelineBadge").textContent = active.length;
}
function renderPipelineBoard(items = pipelineCache) {
  pipelineStages.forEach(([stage]) => {
    const stageItems = items.filter(item => item.pipeline_stage === stage);
    const zone = document.querySelector(`[data-pipeline-dropzone="${stage}"]`);
    if (!zone) return;
    zone.innerHTML = stageItems.length ? stageItems.map(pipelineCard).join("") : `<div class="pipeline-empty">Arraste uma oportunidade para esta etapa.</div>`;
    const count = $(`pipelineColumnCount-${stage}`); if (count) count.textContent = stageItems.length;
    const value = $(`pipelineColumnValue-${stage}`); if (value) value.textContent = money(stageItems.reduce((sum,item) => sum + Number(item.estimated_value || 0), 0), true);
  });
  pipelineSummary(items);
  bindPipelineInteractions();
}
function bindPipelineInteractions() {
  document.querySelectorAll("[data-pipeline-card]").forEach(card => {
    card.ondragstart = event => { draggedPipelineId = card.dataset.pipelineCard; card.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", draggedPipelineId); };
    card.ondragend = () => { draggedPipelineId = null; card.classList.remove("dragging"); document.querySelectorAll(".pipeline-dropzone").forEach(zone => zone.classList.remove("drag-over")); };
  });
  document.querySelectorAll("[data-pipeline-dropzone]").forEach(zone => {
    zone.ondragover = event => { event.preventDefault(); zone.classList.add("drag-over"); };
    zone.ondragleave = () => zone.classList.remove("drag-over");
    zone.ondrop = event => { event.preventDefault(); zone.classList.remove("drag-over"); const id = event.dataTransfer.getData("text/plain") || draggedPipelineId; if (id) movePipeline(id, zone.dataset.pipelineDropzone); };
  });
  document.querySelectorAll("[data-pipeline-stage-select]").forEach(select => {
    select.onchange = event => { event.stopPropagation(); movePipeline(select.dataset.pipelineStageSelect, select.value); };
    select.onclick = event => event.stopPropagation();
  });
}
function populatePipelineUfs(items = []) {
  const select = $("pipelineUfFilter");
  if (!select) return;
  const current = select.value;
  const discovered = items.map(item => String(item.uf || "").trim().toUpperCase()).filter(Boolean);
  const states = [...new Set([...brazilianStates, ...discovered])].sort();
  select.innerHTML = '<option value="">Todos os estados</option>' + states.map(uf => `<option value="${esc(uf)}">${esc(uf)}</option>`).join("");
  select.value = states.includes(current) ? current : "";
}
async function loadPipeline() {
  const params = new URLSearchParams({limit:"500"});
  const search = $("pipelineSearch").value.trim(); if (search) params.set("q", search);
  const stage = $("pipelineStageFilter").value; if (stage) params.set("pipeline_stage", stage);
  const priority = $("pipelinePriorityFilter").value; if (priority) params.set("pipeline_priority", priority);
  const responsible = $("pipelineResponsibleFilter").value.trim(); if (responsible) params.set("pipeline_responsible", responsible);
  const uf = $("pipelineUfFilter").value; if (uf) params.set("uf", uf);
  try {
    let items = await api(`/api/editais?${params}`);
    if ($("pipelineUrgentFilter").checked) items = items.filter(item => { const days = daysUntil(item.proposal_end); return days !== null && days >= 0 && days <= 7; });
    pipelineCache = items;
    populatePipelineUfs(cache.length ? cache : items);
    renderPipelineBoard(items);
  } catch (error) { toast(error.message); }
}
async function movePipeline(id, stage) {
  const item = pipelineCache.find(current => current.id === id) || cache.find(current => current.id === id);
  if (!item || item.pipeline_stage === stage) return;
  try {
    await api(`/api/editais/${id}/pipeline`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({stage})});
    toast(`Movido para ${pipelineStageLabels[stage]}`);
    await Promise.all([loadEditais(), loadPipeline(), dashboard()]);
  } catch (error) { toast(error.message); await loadPipeline(); }
}
async function loadPipelineHistory(id) {
  const list = $("pipelineHistoryList");
  list.innerHTML = '<p class="hint">Carregando histórico...</p>';
  try {
    const events = await api(`/api/editais/${id}/pipeline-history?limit=30`);
    list.innerHTML = events.length ? events.map(event => `<div class="pipeline-history-item"><span></span><div><p>${esc(event.description || "Pipeline atualizado")}</p><small>${esc(pipelineStageLabels[event.to_stage] || "Atualização")}</small></div><time>${esc(dateFmt(event.created_at))}</time></div>`).join("") : '<p class="hint">Nenhuma movimentação registrada.</p>';
  } catch (error) { list.innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
async function openPipelineModal(id) {
  const item = pipelineCache.find(current => current.id === id) || cache.find(current => current.id === id);
  if (!item) return;
  $("pipelineEditalId").value = item.id;
  $("pipelineModalTitle").textContent = item.title;
  $("pipelineModalOrganization").textContent = `${item.organization || "Órgão não informado"} · ${item.uf || "BR"}`;
  $("pipelineModalDeadline").textContent = `Encerramento: ${dateFmt(item.proposal_end)}`;
  $("pipelineModalValue").textContent = money(item.estimated_value);
  $("pipelineStage").value = item.pipeline_stage || "nova_oportunidade";
  $("pipelinePriority").value = item.pipeline_priority || "normal";
  if (!assignableUsersCache.length) await loadAssignableUsers();
  $("pipelineResponsible").innerHTML = assigneeOptions(item.pipeline_responsible_user_id || "");
  $("pipelineResponsible").value = item.pipeline_responsible_user_id || "";
  $("pipelineNotes").value = item.pipeline_notes || "";
  $("pipelineChangeNote").value = "";
  $("pipelineModal").classList.remove("hidden");
  loadPipelineHistory(id);
}
function closePipelineModal() { $("pipelineModal").classList.add("hidden"); $("pipelineForm").reset(); }

const checklistStatusLabels = {
  pendente:"Pendente",
  em_andamento:"Em andamento",
  concluido:"Concluído",
  nao_aplicavel:"Não aplicável"
};

function checklistProgress(items) {
  const applicable = items.filter(item => item.status !== "nao_aplicavel");
  const completed = applicable.filter(item => item.status === "concluido").length;
  return {completed, total:applicable.length, percent:applicable.length ? Math.round(completed / applicable.length * 100) : 0};
}
function assigneeOptions(selectedId = "") {
  const options = ['<option value="">Sem responsável definido</option>'];
  assignableUsersCache.forEach(user => {
    const bitrix = user.bitrix_user_id ? " · Bitrix conectado" : "";
    options.push(`<option value="${esc(user.id)}" ${selectedId === user.id ? "selected" : ""}>${esc(user.full_name)} · ${esc(user.department)}${esc(bitrix)}</option>`);
  });
  return options.join("");
}
function renderChecklist(items = checklistCache) {
  const filter = $("checklistStatusFilter").value;
  const search = ($("checklistSearchInput")?.value || "").trim().toLowerCase();
  const visible = items.filter(item => {
    if (filter && item.status !== filter) return false;
    if (!search) return true;
    return [item.title, item.category, item.description, item.source_reference, item.notes]
      .filter(Boolean).join(" ").toLowerCase().includes(search);
  });
  const progress = checklistProgress(items);
  const pending = items.filter(item => item.status === "pendente").length;
  const doing = items.filter(item => item.status === "em_andamento").length;
  const done = items.filter(item => item.status === "concluido").length;
  $("checklistProgressValue").textContent = `${progress.percent}%`;
  $("checklistProgressText").textContent = items.length ? `${progress.completed} de ${progress.total} itens concluídos` : "Nenhum item gerado";
  $("checklistPendingCount").textContent = pending;
  $("checklistDoingCount").textContent = doing;
  $("checklistDoneCount").textContent = done;
  $("checklistProgressBar").style.width = `${progress.percent}%`;

  const upcoming = items.filter(item => item.due_date && item.status !== "concluido" && item.status !== "nao_aplicavel")
    .sort((a,b) => new Date(a.due_date) - new Date(b.due_date)).slice(0,5);
  $("checklistUpcomingTasks").innerHTML = upcoming.length ? upcoming.map(item => `<article><strong>${esc(item.title)}</strong><span>${esc(dateFmt(item.due_date))}</span></article>`).join("") : '<p class="hint">Nenhuma tarefa com prazo definido.</p>';

  if (!visible.length) {
    $("checklistList").innerHTML = `<div class="checklist-empty-state"><span>✓</span><p>${items.length ? "Nenhuma tarefa encontrada neste filtro." : "Gere o checklist para começar."}</p></div>`;
    return;
  }
  const grouped = new Map();
  visible.forEach(item => {
    if (!grouped.has(item.category)) grouped.set(item.category, []);
    grouped.get(item.category).push(item);
  });
  $("checklistList").innerHTML = [...grouped.entries()].map(([category, categoryItems]) => `
    <section class="checklist-category checklist-table-category">
      <header><div><h4>${esc(category)}</h4><small>${categoryItems.length} tarefa(s)</small></div></header>
      <div class="checklist-category-items">${categoryItems.map(item => `
        <article class="checklist-item checklist-table-row status-${esc(item.status)}">
          <div class="checklist-task-cell">
            <strong>${esc(item.title)}</strong>
            ${item.description ? `<p>${esc(item.description)}</p>` : ""}
            <small>${item.required ? "Obrigatório" : "Opcional"}${item.source_reference ? ` · ${esc(item.source_reference)}` : ""}</small>
          </div>
          <label class="checklist-field-cell"><span>Status</span><select data-checklist-status="${esc(item.id)}">${Object.entries(checklistStatusLabels).map(([key,label]) => `<option value="${key}" ${item.status === key ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          <label class="checklist-field-cell"><span>Responsável cadastrado</span><select data-checklist-responsible="${esc(item.id)}">${assigneeOptions(item.responsible_user_id || "")}</select></label>
          <label class="checklist-field-cell"><span>Prazo</span><input type="datetime-local" data-checklist-due-date="${esc(item.id)}" value="${item.due_date ? esc(new Date(item.due_date).toISOString().slice(0,16)) : ""}"></label>
          <label class="checklist-field-cell checklist-notes-cell"><span>Observações</span><textarea rows="2" data-checklist-notes="${esc(item.id)}" placeholder="Pendências ou orientação">${esc(item.notes || "")}</textarea></label>
          <button class="primary compact checklist-save-button" type="button" data-save-checklist="${esc(item.id)}">Salvar</button>
        </article>`).join("")}</div>
    </section>`).join("");
}
async function loadAssignableUsers() {
  try { assignableUsersCache = await api("/api/team/assignable"); }
  catch (error) { assignableUsersCache = []; toast(error.message); }
}
async function loadChecklist(id) {
  $("checklistList").innerHTML = '<p class="hint">Carregando checklist...</p>';
  try {
    checklistCache = await api(`/api/editais/${id}/checklist`);
    renderChecklist();
  } catch (error) {
    $("checklistList").innerHTML = `<p class="hint">${esc(error.message)}</p>`;
  }
}
async function openChecklistModal(id) {
  const item = cache.find(current => current.id === id) || pipelineCache.find(current => current.id === id);
  if (!item) return;
  activeChecklistEditalId = id;
  checklistCache = [];
  $("checklistModalTitle").textContent = item.title;
  $("checklistModalSubtitle").textContent = `${item.organization || "Órgão não informado"} · ${item.municipality || "Município não informado"} / ${item.uf || "BR"}`;
  $("checklistOrganization").textContent = item.organization || "Não informado";
  $("checklistDeadline").textContent = dateFmt(item.proposal_end);
  $("checklistGeneralResponsible").textContent = item.pipeline_responsible || "Não definido";
  $("checklistSource").textContent = item.source === "amunes_licitamunes" ? "AMUNES / LicitaMunes" : (item.source || "PNCP").toUpperCase();
  $("checklistGenerationMode").textContent = "Checklist operacional com alertas automáticos integrados ao Bitrix e e-mail.";
  $("checklistStatusFilter").value = "";
  if ($("checklistSearchInput")) $("checklistSearchInput").value = "";
  $("checklistModal").classList.remove("hidden");
  document.body.classList.add("checklist-workspace-open");
  await loadAssignableUsers();
  await loadChecklist(id);
  await activateChecklistTab("checklist");
}
function closeChecklistModal() {
  $("checklistModal").classList.add("hidden");
  document.body.classList.remove("checklist-workspace-open");
  activeChecklistEditalId = null;
  checklistCache = [];
}

function renderWorkspaceSchedule() {
  const target = $("checklistSchedule");
  if (!target) return;
  const items = checklistCache.filter(item => item.due_date).sort((a,b) => new Date(a.due_date) - new Date(b.due_date));
  $("scheduleSummary").textContent = `${items.length} tarefa(s) com prazo`;
  if (!items.length) { target.innerHTML = '<p class="hint">Defina prazos nas tarefas para montar o cronograma.</p>'; return; }
  target.innerHTML = items.map(item => `<article><time>${esc(dateFmt(item.due_date))}</time><div><strong>${esc(item.title)}</strong><span>${esc(item.category)} · ${esc(checklistStatusLabels[item.status] || item.status)}</span></div><b class="schedule-status status-${esc(item.status)}"></b></article>`).join("");
}
async function loadWorkspaceDocuments() {
  if (!activeChecklistEditalId || !$("workspaceDocuments")) return;
  $("workspaceDocuments").innerHTML = '<p class="hint">Carregando documentos...</p>';
  try {
    const docs = await api(`/api/editais/${activeChecklistEditalId}/documents`);
    if (!docs.length) { $("workspaceDocuments").innerHTML = '<div class="checklist-empty-state"><span>↥</span><p>Nenhum documento anexado.</p></div>'; return; }
    $("workspaceDocuments").innerHTML = docs.map(doc => `<article><div class="document-file-icon">${doc.mime_type === 'application/pdf' ? 'PDF' : 'DOC'}</div><div><strong>${esc(doc.title)}</strong><span>${esc(doc.document_type || 'Documento')} · ${esc(doc.status || 'pendente')}</span></div>${doc.download_url ? `<a class="ghost compact" href="${esc(doc.download_url)}" target="_blank">Abrir</a>` : ''}</article>`).join('');
  } catch (error) { $("workspaceDocuments").innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
async function uploadWorkspaceFiles(files) {
  if (!activeChecklistEditalId || !files?.length) return;
  const status = $("workspaceUploadStatus");
  const category = $("workspaceDocumentCategory")?.value || 'Documento da concorrência';
  let completed = 0;
  for (const file of files) {
    status.textContent = `Enviando ${file.name} (${completed + 1}/${files.length})...`;
    const form = new FormData(); form.append('file', file); form.append('category', category);
    try { await api(`/api/editais/${activeChecklistEditalId}/documents`, {method:'POST', body:form}); completed += 1; }
    catch (error) { toast(`${file.name}: ${error.message}`); }
  }
  status.textContent = `${completed} de ${files.length} arquivo(s) processado(s).`;
  $("workspaceFileInput").value = '';
  await Promise.all([loadWorkspaceDocuments(), loadWorkspaceHistory(), loadChecklist(activeChecklistEditalId)]);
}
function renderWorkspaceTeam() {
  const target = $("workspaceTeam"); if (!target) return;
  const item = cache.find(current => current.id === activeChecklistEditalId) || pipelineCache.find(current => current.id === activeChecklistEditalId);
  const taskOwners = new Map();
  checklistCache.forEach(task => { if (task.responsible_user_id) taskOwners.set(task.responsible_user_id, task.responsible || 'Responsável'); });
  const cards = [{role:'Responsável geral', name:item?.pipeline_responsible || 'Não definido'}, ...[...taskOwners.values()].map(name => ({role:'Responsável por tarefas', name}))];
  target.innerHTML = cards.map(card => `<article><div class="team-avatar">${esc((card.name || '?').slice(0,1).toUpperCase())}</div><div><small>${esc(card.role)}</small><strong>${esc(card.name)}</strong></div></article>`).join('');
}
async function loadWorkspaceHistory() {
  if (!activeChecklistEditalId || !$("workspaceHistory")) return;
  try {
    const events = await api(`/api/editais/${activeChecklistEditalId}/pipeline-history?limit=100`);
    if (!events.length) { $("workspaceHistory").innerHTML = '<p class="hint">Nenhuma movimentação registrada.</p>'; return; }
    $("workspaceHistory").innerHTML = events.map(event => `<article><time>${esc(new Date(event.created_at).toLocaleString('pt-BR'))}</time><div><strong>${esc(event.description || 'Atualização da concorrência')}</strong><span>${esc(event.event_type.replaceAll('_',' '))}</span></div></article>`).join('');
  } catch (error) { $("workspaceHistory").innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
async function activateChecklistTab(name) {
  document.querySelectorAll('[data-checklist-tab]').forEach(tab => tab.classList.toggle('active', tab.dataset.checklistTab === name));
  document.querySelectorAll('[data-checklist-panel]').forEach(panel => panel.classList.toggle('active', panel.dataset.checklistPanel === name));
  if (name === 'cronograma') renderWorkspaceSchedule();
  if (name === 'documentos') await loadWorkspaceDocuments();
  if (name === 'equipe') renderWorkspaceTeam();
  if (name === 'historico') await loadWorkspaceHistory();
}

async function generateActiveChecklist() {
  if (!activeChecklistEditalId) return;
  const button = $("generateChecklistButton");
  if (checklistCache.length && !confirm("Gerar novamente substituirá o checklist atual e o andamento dos itens. Deseja continuar?")) return;
  button.disabled = true;
  button.textContent = "Gerando checklist...";
  try {
    const result = await api(`/api/editais/${activeChecklistEditalId}/checklist/generate`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({replace_existing:true})
    });
    checklistCache = result.items || [];
    $("checklistGenerationMode").textContent = result.mode === "openai" ? "Checklist interpretado pela IA OpenAI com base nos documentos." : "Checklist gerado pela IA local com análise dos documentos indexados.";
    renderChecklist();
    toast(`${checklistCache.length} itens adicionados ao checklist`);
    await Promise.all([loadEditais(), loadPipeline(), dashboard()]);
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = "✦ Gerar checklist com IA"; }
}
async function saveChecklistItem(id, changes) {
  try {
    const updated = await api(`/api/checklist-items/${id}`, {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(changes)
    });
    checklistCache = checklistCache.map(item => item.id === id ? updated : item);
    renderChecklist();
    toast("Checklist atualizado");
    await Promise.all([loadEditais(), loadPipeline(), dashboard()]);
  } catch (error) { toast(error.message); }
}
async function downloadActiveChecklistPdf() {
  if (!activeChecklistEditalId) return;
  if (!checklistCache.length) { toast("Gere o checklist antes de baixar o PDF"); return; }
  try {
    toast("Gerando checklist PDF...");
    await downloadPdf(`/api/editais/${activeChecklistEditalId}/checklist/report`, {}, "Checklist_Operacional_HORUS_CONNECTIVE.pdf");
    toast("Checklist baixado com sucesso");
  } catch (error) { toast(error.message); }
}

async function generateReportForIds(ids, title = "Relatório de Concorrências Selecionadas") {
  if (!ids.length) { toast("Selecione ao menos uma concorrência"); return; }
  try {
    toast("Gerando relatório PDF...");
    await downloadPdf("/api/reports/competitions", {edital_ids:ids, title}, "Relatorio_Concorrencias_HORUS_CONNECTIVE.pdf");
    toast("Relatório gerado com sucesso");
  } catch (error) { toast(error.message); }
}

function monitorStatusText(status) {
  return ({queued:"Na fila",running:"Executando",completed:"Concluído",completed_with_warnings:"Concluído com alertas",failed:"Falhou",cancelled:"Cancelado"})[status] || status || "Sem execução";
}
function fillMonitorForm(config) {
  $("monitorEnabled").checked = Boolean(config.enabled);
  $("monitorTime").value = `${String(config.hour ?? 7).padStart(2,"0")}:${String(config.minute ?? 0).padStart(2,"0")}`;
  $("monitorLookback").value = String(config.lookback_days || 1);
  $("monitorUf").value = config.uf || "";
  $("monitorMaxPages").value = config.max_pages || 5;
  $("monitorKeywords").value = (config.keywords || []).join(", ");
  document.querySelectorAll('[name="monitorModalidade"]').forEach(input => { input.checked = (config.modalities || []).includes(Number(input.value)); });
  $("monitorDownloadDocuments").checked = Boolean(config.download_documents);
  $("monitorGenerateReport").checked = Boolean(config.generate_report);
  $("monitorStatusLabel").textContent = config.enabled ? "Ativo" : "Pausado";
  $("monitorStatusLabel").className = config.enabled ? "monitor-active" : "";
  $("monitorNavBadge").textContent = config.enabled ? "Ativo" : "Pausado";
  $("monitorNextRun").textContent = config.next_run_at ? dateFmt(config.next_run_at) : "Não agendada";
  $("monitorLastRun").textContent = config.last_run_at ? dateFmt(config.last_run_at) : "Nunca executado";
  const summary = config.last_summary || {};
  $("monitorLastSummary").textContent = config.last_run_at ? `${summary.created || 0} novas · ${summary.updated || 0} atualizadas` : "Sem dados";
  $("monitorOpenReportButton").disabled = !config.last_report_path;
}
async function loadMonitorConfig() {
  try {
    const config = await api("/api/monitor/config");
    fillMonitorForm(config);
    await loadMonitorHistory();
  } catch (error) { toast(error.message); }
}
async function loadMonitorHistory() {
  try {
    const jobs = await api("/api/jobs?limit=50");
    const monitorJobs = jobs.filter(job => job.job_type === "daily_monitor").slice(0, 12);
    $("monitorHistoryList").innerHTML = monitorJobs.length ? monitorJobs.map(job => {
      const result = job.result || {};
      return `<article class="monitor-history-item"><span class="monitor-history-dot status-${esc(job.status)}"></span><div><strong>${esc(monitorStatusText(job.status))}</strong><p>${Number(result.created || 0)} nova(s), ${Number(result.updated || 0)} atualizada(s), ${Number(result.records_found || 0)} localizada(s)</p><small>${esc(dateFmt(job.created_at))}</small></div>${result.report_path ? '<button class="ghost compact" data-open-monitor-report="true">PDF</button>' : ""}</article>`;
    }).join("") : '<p class="hint">Nenhum monitoramento executado.</p>';
  } catch (error) { $("monitorHistoryList").innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
async function pollMonitorJob(id) {
  monitorJobId = id;
  setStatus($("monitorStatusBox"), "Monitoramento em execução...");
  $("monitorStatusBox").classList.remove("hidden");
  for (;;) {
    const job = await api(`/api/jobs/${id}`);
    const result = job.result || {};
    setStatus($("monitorStatusBox"), `${monitorStatusText(job.status)} · ${result.records_found || 0} localizada(s) · ${result.created || 0} nova(s)`, job.status === "failed" ? "error" : job.status === "completed" ? "success" : "");
    if (["completed","completed_with_warnings","failed","cancelled"].includes(job.status)) {
      monitorJobId = null;
      await Promise.all([loadMonitorConfig(), loadEditais(), dashboard(), history()]);
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 1600));
  }
}
async function runMonitorNow() {
  const button = $("monitorRunNowButton");
  button.disabled = true;
  try {
    const job = await api("/api/monitor/run", {method:"POST"});
    pollMonitorJob(job.id);
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
}



async function loadSegmentSettings() {
  try {
    const config = await api("/api/monitor/config");
    $("segmentName").value = config.segment_name || "Publicidade e propaganda";
    $("segmentExactEnabled").checked = Boolean(config.exact_match_enabled);
    $("segmentExactPhrases").value = (config.exact_phrases || []).join("\n");
  } catch (error) { toast(error.message); }
}
async function saveSegmentSettings(event) {
  event.preventDefault();
  try {
    const current = await api("/api/monitor/config");
    const phrases = $("segmentExactPhrases").value.split(/\n|,/).map(value => value.trim()).filter(Boolean);
    const payload = {...current, segment_name: $("segmentName").value.trim(), exact_match_enabled: $("segmentExactEnabled").checked, exact_phrases: phrases};
    ["id","last_run_at","last_status","last_report_path","last_summary","updated_at","next_run_at"].forEach(key => delete payload[key]);
    const config = await api("/api/monitor/config", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    setStatus($("segmentSettingsStatus"), config.exact_match_enabled ? `Perfil salvo: somente editais aderentes a ${config.segment_name}.` : "Perfil salvo. A busca exata está desativada.", "success");
    $("segmentSettingsStatus").classList.remove("hidden"); toast("Perfil de busca salvo");
  } catch (error) { setStatus($("segmentSettingsStatus"), error.message, "error"); $("segmentSettingsStatus").classList.remove("hidden"); }
}

function renderUsers() {
  const search = ($("usersSearch")?.value || "").trim().toLowerCase();
  const items = usersCache.filter(user => !search || `${user.full_name} ${user.username} ${user.email} ${user.department} ${user.phone_voip || ""} ${user.bitrix_user_id || ""}`.toLowerCase().includes(search));
  if ($("usersTotalCount")) $("usersTotalCount").textContent = usersCache.length;
  if ($("usersActiveCount")) $("usersActiveCount").textContent = usersCache.filter(user => user.is_active).length;
  if ($("usersDepartmentCount")) $("usersDepartmentCount").textContent = new Set(usersCache.map(user => user.department).filter(Boolean)).size;
  if (!$("usersList")) return;
  $("usersList").innerHTML = items.length ? items.map(user => {
    const badge = user.is_admin ? '<span class="user-status admin">Administrador</span>' : `<span class="user-status ${user.is_active ? "" : "inactive"}">${user.is_active ? "Ativo" : "Inativo"}</span>`;
    const permissionCount = user.is_admin ? "Todos os módulos" : `${(user.permissions || []).length} módulo(s)`;
    return `<article class="user-row">
      <div class="user-identity"><span class="user-avatar-large">${esc((user.full_name || "U").slice(0,1).toUpperCase())}</span><div><strong>${esc(user.full_name)}</strong><small>@${esc(user.username)} · ${esc(user.email)}</small></div></div>
      <div class="user-meta"><strong>${esc(user.department)}</strong><small>${esc(user.phone_voip || "Telefone/VoIP não informado")}</small><small>${user.bitrix_user_id ? `Bitrix ID ${esc(user.bitrix_user_id)}` : "Bitrix não vinculado"} · ${user.notify_email ? "E-mail ativo" : "E-mail inativo"} · ${user.notify_bitrix ? "Chat ativo" : "Chat inativo"}</small></div>
      <div class="user-meta">${badge}<small>${esc(permissionCount)}${user.last_login_at ? ` · Último acesso ${esc(dateFmt(user.last_login_at))}` : " · Nunca acessou"}</small></div>
      <div class="user-actions"><button class="ghost compact" type="button" data-edit-user="${esc(user.id)}">Editar</button><button class="ghost compact" type="button" data-reset-user-password="${esc(user.id)}">Senha</button>${user.is_admin ? "" : `<button class="ghost compact" type="button" data-toggle-user="${esc(user.id)}">${user.is_active ? "Desativar" : "Ativar"}</button>`}</div>
    </article>`;
  }).join("") : '<p class="hint">Nenhum usuário encontrado.</p>';
}
async function loadUsers() {
  if (!isAdministrator || !$("usersList")) return;
  try { usersCache = await api("/api/users"); renderUsers(); }
  catch (error) { $("usersList").innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
function openUserModal(userId = null) {
  if (!$("userModal")) return;
  const user = userId ? usersCache.find(item => item.id === userId) : null;
  $("userModalTitle").textContent = user ? "Editar usuário" : "Novo usuário";
  $("userId").value = user?.id || "";
  $("userFullName").value = user?.full_name || "";
  $("userUsername").value = user?.username || "";
  $("userUsername").disabled = Boolean(user?.is_admin);
  $("userEmail").value = user?.email || "";
  $("userDepartment").value = user?.department || "";
  $("userPhone").value = user?.phone_voip || "";
  $("userBitrixId").value = user?.bitrix_user_id || "";
  $("userNotifyEmail").checked = user ? user.notify_email : true;
  $("userNotifyBitrix").checked = user ? user.notify_bitrix : true;
  $("userPassword").value = "";
  $("userPassword").required = !user;
  $("userPasswordLabel").classList.toggle("hidden", Boolean(user));
  $("userActive").checked = user ? user.is_active : true;
  $("userActive").disabled = Boolean(user?.is_admin);
  document.querySelectorAll('[name="userPermission"]').forEach(box => { box.checked = Boolean(user?.is_admin || user?.permissions?.includes(box.value)); box.disabled = Boolean(user?.is_admin); });
  $("userFormStatus").classList.add("hidden");
  $("userModal").classList.remove("hidden");
}
function closeUserModal() { if ($("userModal")) $("userModal").classList.add("hidden"); }
function openPasswordResetModal(userId) {
  const user = usersCache.find(item => item.id === userId); if (!user || !$("passwordResetModal")) return;
  $("passwordResetUserId").value = user.id; $("passwordResetValue").value = ""; $("passwordResetUserName").textContent = `Nova senha para ${user.full_name} (@${user.username}).`;
  $("passwordResetModal").classList.remove("hidden"); $("passwordResetValue").focus();
}
function closePasswordResetModal() { if ($("passwordResetModal")) $("passwordResetModal").classList.add("hidden"); }
async function toggleUserStatus(userId) {
  const user = usersCache.find(item => item.id === userId); if (!user || user.is_admin) return;
  try {
    await api(`/api/users/${user.id}`, {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({username:user.username,email:user.email,full_name:user.full_name,department:user.department,phone_voip:user.phone_voip,bitrix_user_id:user.bitrix_user_id,notify_email:user.notify_email,notify_bitrix:user.notify_bitrix,is_active:!user.is_active,permissions:user.permissions || []})});
    toast(user.is_active ? "Usuário desativado" : "Usuário ativado"); await loadUsers();
  } catch (error) { toast(error.message); }
}

function notificationStatusLabel(value) {
  return ({completed:"Concluído",completed_with_warnings:"Com alertas",failed:"Falhou",paused:"Pausado"})[value] || value || "Nunca executado";
}
function fillNotificationConfig(config) {
  notificationConfigCache = config;
  $("notificationEnabled").checked = Boolean(config.enabled);
  $("notificationTime").value = `${String(config.hour ?? 8).padStart(2,"0")}:${String(config.minute ?? 0).padStart(2,"0")}`;
  $("notificationEmailEnabled").checked = Boolean(config.email_enabled);
  $("notificationBitrixEnabled").checked = Boolean(config.bitrix_enabled);
  $("notificationSmtpHost").value = config.smtp_host || "";
  $("notificationSmtpPort").value = String(config.smtp_port || 587);
  $("notificationSmtpUsername").value = config.smtp_username || "";
  $("notificationSenderEmail").value = config.smtp_sender_email || "";
  $("notificationSenderName").value = config.smtp_sender_name || "Hórus Connective";
  $("notificationUseTls").checked = Boolean(config.smtp_use_tls);
  $("notificationUseSsl").checked = Boolean(config.smtp_use_ssl);
  $("notificationBitrixWebhook").value = "";
  $("notificationSmtpPassword").value = "";
  $("notificationClearBitrix").checked = false;
  $("notificationClearSmtp").checked = false;
  $("notificationRoutineStatus").textContent = config.enabled ? "Ativa" : "Pausada";
  $("notificationNextRun").textContent = config.next_run_at ? dateFmt(config.next_run_at) : (config.enabled ? "Ao iniciar o agendamento" : "—");
  $("notificationLastRun").textContent = config.last_run_at ? dateFmt(config.last_run_at) : "Nunca";
  const summary = config.last_summary || {};
  $("notificationLastSummary").textContent = config.last_run_at ? `${summary.sent || 0} envio(s) · ${summary.failed || 0} falha(s)` : "—";
  $("bitrixConfiguredBadge").textContent = config.bitrix_webhook_configured ? "Configurado" : "Não configurado";
  $("bitrixConfiguredBadge").classList.toggle("configured", Boolean(config.bitrix_webhook_configured));
  $("smtpConfiguredBadge").textContent = config.smtp_password_configured && config.smtp_host ? "Configurado" : "Não configurado";
  $("smtpConfiguredBadge").classList.toggle("configured", Boolean(config.smtp_password_configured && config.smtp_host));
}
async function loadNotificationHistory() {
  if (!isAdministrator || !$("notificationHistoryList")) return;
  try {
    const items = await api("/api/notifications/history?limit=50");
    $("notificationHistoryList").innerHTML = items.length ? items.map(item => `<article class="notification-history-item"><span class="notification-history-dot ${esc(item.status)}"></span><div><strong>${esc(item.user_name || "Usuário removido")} · ${item.channel === "bitrix" ? "Bitrix24" : "E-mail"}</strong><small>${esc(item.status === "sent" ? `${item.item_count} etapa(s) enviada(s) para ${item.recipient || "destinatário"}` : item.error_message || "Falha no envio")}</small></div><time>${esc(dateFmt(item.created_at))}</time></article>`).join("") : '<p class="hint">Nenhum envio registrado.</p>';
  } catch (error) { $("notificationHistoryList").innerHTML = `<p class="hint">${esc(error.message)}</p>`; }
}
async function loadNotificationConfig() {
  if (!isAdministrator || !$("notificationConfigForm")) return;
  try {
    const [config, users] = await Promise.all([api("/api/notifications/config"), api("/api/team/assignable")]);
    assignableUsersCache = users;
    fillNotificationConfig(config);
    $("notificationTestUser").innerHTML = '<option value="">Selecione um usuário</option>' + users.map(user => `<option value="${esc(user.id)}">${esc(user.full_name)} · ${esc(user.department)}</option>`).join("");
    await loadNotificationHistory();
  } catch (error) { setStatus($("notificationStatusBox"), error.message, "error"); $("notificationStatusBox").classList.remove("hidden"); }
}
async function saveNotificationConfig(event) {
  event.preventDefault();
  const [hour, minute] = $("notificationTime").value.split(":").map(Number);
  const payload = {
    enabled:$("notificationEnabled").checked,hour,minute,
    email_enabled:$("notificationEmailEnabled").checked,bitrix_enabled:$("notificationBitrixEnabled").checked,
    bitrix_webhook_url:$("notificationBitrixWebhook").value.trim() || null,clear_bitrix_webhook:$("notificationClearBitrix").checked,
    smtp_host:$("notificationSmtpHost").value.trim() || null,smtp_port:Number($("notificationSmtpPort").value || 587),smtp_username:$("notificationSmtpUsername").value.trim() || null,
    smtp_password:$("notificationSmtpPassword").value || null,clear_smtp_password:$("notificationClearSmtp").checked,smtp_sender_email:$("notificationSenderEmail").value.trim() || null,
    smtp_sender_name:$("notificationSenderName").value.trim() || "Hórus Connective",smtp_use_tls:$("notificationUseTls").checked,smtp_use_ssl:$("notificationUseSsl").checked
  };
  try {
    const config = await api("/api/notifications/config", {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    fillNotificationConfig(config); setStatus($("notificationStatusBox"), "Configuração salva. Execute o arquivo de agendamento do Windows para enviar com o Hórus fechado.", "success"); $("notificationStatusBox").classList.remove("hidden"); toast("Notificações salvas");
  } catch (error) { setStatus($("notificationStatusBox"), error.message, "error"); $("notificationStatusBox").classList.remove("hidden"); }
}
async function sendNotificationTest() {
  const userId = $("notificationTestUser").value;
  const channels = [$("notificationTestEmail").checked ? "email" : null,$("notificationTestBitrix").checked ? "bitrix" : null].filter(Boolean);
  if (!userId || !channels.length) { toast("Selecione o usuário e ao menos um canal"); return; }
  const button = $("notificationTestButton"); button.disabled = true;
  try {
    const result = await api("/api/notifications/test", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:userId,channels})});
    const failed = (result.results || []).filter(item => item.status !== "sent");
    setStatus($("notificationStatusBox"), failed.length ? failed.map(item => `${item.channel}: ${item.error}`).join(" · ") : "Mensagem de teste enviada com sucesso.", failed.length ? "error" : "success");
    $("notificationStatusBox").classList.remove("hidden"); await loadNotificationHistory();
  } catch (error) { setStatus($("notificationStatusBox"), error.message, "error"); $("notificationStatusBox").classList.remove("hidden"); }
  finally { button.disabled = false; }
}
async function runNotificationsNow() {
  try { await api("/api/notifications/run", {method:"POST"}); toast("Envio diário iniciado"); setTimeout(loadNotificationConfig, 1800); }
  catch (error) { toast(error.message); }
}

function openDrawer(id) {
  const item = cache.find(edital => edital.id === id); if (!item) return;
  const score = opportunityScore(item); const deadline = deadlineText(item.proposal_end);
  $("drawerTitle").textContent = item.title;
  $("drawerContent").innerHTML = `<div class="detail-score"><div class="score-ring" style="--score:${score}%"><strong>${score}%</strong></div><div><h3>${scoreLabel(score)}</h3><p class="hint">Score preliminar calculado por objeto, valor, prazo e indexação.</p></div></div><div class="detail-grid"><div class="detail-item"><small>Órgão</small><strong>${esc(item.organization || "Não informado")}</strong></div><div class="detail-item"><small>Município / UF</small><strong>${esc([item.municipality, item.uf || "BR"].filter(Boolean).join(" / "))}</strong></div><div class="detail-item"><small>Modalidade</small><strong>${esc(item.modality_name || item.source)}</strong></div><div class="detail-item"><small>Valor estimado</small><strong>${esc(money(item.estimated_value))}</strong></div><div class="detail-item"><small>Encerramento</small><strong>${esc(dateFmt(item.proposal_end))}</strong></div><div class="detail-item"><small>Publicação</small><strong>${esc(dateFmt(item.publication_date))}</strong></div><div class="detail-item"><small>Situação</small><strong>${esc(item.status_name || deadline.text)}</strong></div><div class="detail-item"><small>Fonte</small><strong>${esc(item.source === "amunes_licitamunes" ? "AMUNES / LicitaMunes" : (item.source || "PNCP").toUpperCase())}</strong></div><div class="detail-item"><small>Etapa</small><strong>${esc(pipelineStageLabels[item.pipeline_stage] || "Nova oportunidade")}</strong></div><div class="detail-item"><small>Prioridade</small><strong>${esc(pipelinePriorityLabels[item.pipeline_priority] || "Normal")}</strong></div><div class="detail-item"><small>Responsável</small><strong>${esc(item.pipeline_responsible || "Não definido")}</strong></div></div><div class="detail-section"><small>Objeto</small><p>${esc(item.object_text || "Sem descrição")}</p></div>${item.source_url ? `<div class="detail-official-link"><a class="primary" href="${esc(item.source_url)}" target="_blank" rel="noopener">Abrir publicação oficial</a></div>` : ""}<div class="detail-actions"><button class="primary" data-open-pipeline="${esc(item.id)}">Gerenciar no pipeline</button><button class="ghost" data-open-checklist="${esc(item.id)}">Checklist IA</button><button class="ghost" data-analyze-edital="${esc(item.id)}">Analisar com IA</button><button class="favorite-button ${favorites.has(item.id) ? "active" : ""}" data-favorite="${esc(item.id)}">★ Favoritar</button></div>`;
  $("drawerBackdrop").classList.remove("hidden"); $("detailDrawer").classList.add("open"); $("detailDrawer").setAttribute("aria-hidden", "false");
}
function closeDrawer() { $("drawerBackdrop").classList.add("hidden"); $("detailDrawer").classList.remove("open"); $("detailDrawer").setAttribute("aria-hidden", "true"); }

function formatDatetimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  const pad = num => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function openEditalModal(id) {
  const item = cache.find(edital => edital.id === id);
  if (!item) return;
  $("editalId").value = item.id;
  $("editalTitle").value = item.title || "";
  $("editalOrganization").value = item.organization || "";
  $("editalUf").value = item.uf || "";
  $("editalMunicipality").value = item.municipality || "";
  $("editalModality").value = item.modality_name || "";
  $("editalStatus").value = item.status_name || "";
  $("editalValue").value = item.estimated_value ?? "";
  $("editalProposalEnd").value = formatDatetimeLocal(item.proposal_end);
  $("editalObject").value = item.object_text || "";
  $("editalModal").classList.remove("hidden");
}
function closeEditalModal() { $("editalModal").classList.add("hidden"); $("editalForm").reset(); }
function requestDeleteEdital(id) {
  const item = cache.find(edital => edital.id === id);
  if (!item) return;
  pendingDeleteEditalId = id;
  $("deleteEditalMessage").textContent = `Você está prestes a excluir “${item.title}”.`;
  $("deleteEditalModal").classList.remove("hidden");
}
function closeDeleteEditalModal() {
  pendingDeleteEditalId = null;
  $("deleteEditalModal").classList.add("hidden");
}
async function confirmDeleteEdital() {
  const id = pendingDeleteEditalId;
  if (!id) return;
  const button = $("confirmDeleteEdital");
  button.disabled = true;
  button.textContent = "Excluindo...";
  try {
    await api(`/api/editais/${id}`, {method:"DELETE"});
    favorites.delete(id);
    selectedEditais.delete(id);
    saveFavorites();
    selection();
    closeDeleteEditalModal();
    toast("Edital excluído com sucesso");
    await Promise.all([loadEditais(), dashboard()]);
    renderRadar();
    renderFavorites();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Excluir definitivamente";
  }
}

function commandResults(query = "") {
  const modules = Object.entries(titles).map(([view,title]) => ({type:"view", id:view, title, subtitle:"Abrir módulo"}));
  const editais = cache.filter(item => `${item.title} ${item.organization || ""}`.toLowerCase().includes(query.toLowerCase())).slice(0, 8).map(item => ({type:"edital", id:item.id, title:item.title, subtitle:item.organization || "Órgão não informado"}));
  const items = query ? editais : modules;
  $("commandResults").innerHTML = items.map(item => `<div class="command-result" data-command-type="${item.type}" data-command-id="${esc(item.id)}"><div><strong>${esc(item.title)}</strong><small>${esc(item.subtitle)}</small></div><span>→</span></div>`).join("");
}
function openCommand() { $("commandPalette").classList.remove("hidden"); $("commandSearch").value = ""; commandResults(); setTimeout(() => $("commandSearch").focus(), 20); }
function closeCommand() { $("commandPalette").classList.add("hidden"); }

async function health() { try { await api("/health"); $("healthDot").classList.add("ok"); $("healthBadge").textContent = "Sistema operacional"; } catch { $("healthBadge").textContent = "Sistema indisponível"; } }
function progress(job) { const p = job.result?.progress || {}; const value = Number(p.percent || 0); $("progressWrap").classList.remove("hidden"); $("progressBar").style.width = `${value}%`; $("progressPercent").textContent = `${value}%`; $("progressMessage").textContent = p.message || job.status; $("progressStats").textContent = `Encontrados: ${job.result?.records_found || 0} · Novos: ${job.result?.created || 0} · Atualizados: ${job.result?.updated || 0}`; }
async function poll(id) { activeJobId = id; $("cancelJobButton").classList.remove("hidden"); for (;;) { const job = await api(`/api/jobs/${id}`); progress(job); setStatus($("jobStatus"), job.error_message || job.result?.progress?.message || job.status, job.status === "failed" ? "error" : ""); if (["completed","completed_with_warnings","failed","cancelled"].includes(job.status)) { activeJobId = null; $("cancelJobButton").classList.add("hidden"); await Promise.all([loadEditais(), dashboard(), history()]); return; } await new Promise(resolve => setTimeout(resolve, 1500)); } }
async function history() { const jobs = await api("/api/jobs?limit=20"); $("historyList").innerHTML = jobs.length ? jobs.map(job => `<div class="history-item"><div><strong>${esc(job.status)}</strong><p>${esc(job.result?.progress?.message || "Sincronização PNCP")}</p><small>${esc(dateFmt(job.created_at))}</small></div></div>`).join("") : "<p class='hint'>Nenhuma sincronização.</p>"; }

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 ** 2)).toFixed(1)} MB`;
}
function reportIcon(category) {
  if (category === "Checklist operacional") return "✓";
  if (category === "Monitoramento diário") return "◷";
  return "▤";
}
function filteredSavedReports() {
  const query = $("reportsSearch")?.value.trim().toLowerCase() || "";
  const category = $("reportsCategoryFilter")?.value || "";
  return savedReportsCache.filter(item => {
    const categoryMatches = !category || item.category === category;
    const queryMatches = !query || `${item.name} ${item.category}`.toLowerCase().includes(query);
    return categoryMatches && queryMatches;
  });
}
function renderSavedReports() {
  const items = filteredSavedReports();
  const list = $("reportsList");
  if (!list) return;
  if (!items.length) {
    list.innerHTML = `<div class="reports-empty"><span>▣</span><strong>Nenhum relatório encontrado</strong><p>Gere um checklist ou relatório de concorrências para vê-lo aqui.</p></div>`;
    return;
  }
  list.innerHTML = items.map(item => `<article class="report-row">
    <div class="report-icon">${reportIcon(item.category)}</div>
    <div class="report-main"><strong title="${esc(item.name)}">${esc(item.name)}</strong><small>${esc(item.relative_path)}</small></div>
    <span class="report-category">${esc(item.category)}</span>
    <div class="report-meta"><strong>${esc(formatFileSize(item.size_bytes))}</strong><small>${esc(dateFmt(item.modified_at))}</small></div>
    <div class="report-actions"><button class="ghost compact" type="button" data-open-saved-report="${esc(item.id)}">Abrir PDF</button><button class="danger compact" type="button" data-delete-saved-report="${esc(item.id)}" data-report-name="${esc(item.name)}">Excluir</button></div>
  </article>`).join("");
}
async function loadSavedReports() {
  const list = $("reportsList");
  if (list) list.innerHTML = '<p class="hint">Carregando relatórios...</p>';
  try {
    const data = await api("/api/reports/saved");
    savedReportsCache = data.items || [];
    const checklistCount = savedReportsCache.filter(item => item.category === "Checklist operacional").length;
    if ($("reportsTotalCount")) $("reportsTotalCount").textContent = savedReportsCache.length;
    if ($("reportsChecklistCount")) $("reportsChecklistCount").textContent = checklistCount;
    if ($("reportsOtherCount")) $("reportsOtherCount").textContent = Math.max(0, savedReportsCache.length - checklistCount);
    if ($("reportsTotalSize")) $("reportsTotalSize").textContent = formatFileSize(data.total_size_bytes || 0);
    if ($("reportsNavBadge")) $("reportsNavBadge").textContent = savedReportsCache.length;
    renderSavedReports();
  } catch (error) {
    if (list) list.innerHTML = `<p class="hint">${esc(error.message)}</p>`;
  }
}
async function openSavedReport(id) {
  if (window.pywebview?.api?.open_saved_report) {
    const result = await window.pywebview.api.open_saved_report(id);
    if (!result?.ok) toast(result?.error || "Não foi possível abrir o relatório");
    return;
  }
  const link = document.createElement("a");
  link.href = `/api/reports/saved/${encodeURIComponent(id)}`;
  link.target = "_blank";
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
}
async function deleteSavedReport(id, name) {
  if (!confirm(`Excluir definitivamente o relatório "${name}"?`)) return;
  try {
    await api(`/api/reports/saved/${encodeURIComponent(id)}`, {method:"DELETE"});
    toast("Relatório excluído");
    await loadSavedReports();
  } catch (error) { toast(error.message); }
}
async function openReportsFolder() {
  if (!window.pywebview?.api?.open_reports_folder) {
    toast("A pasta de relatórios está disponível no aplicativo desktop.");
    return;
  }
  const result = await window.pywebview.api.open_reports_folder();
  toast(result?.ok ? "Pasta de relatórios aberta" : "Não foi possível abrir a pasta");
}

$("menuToggle").onclick = () => $("sidebar").classList.toggle("open");
$("globalSyncButton").onclick = () => switchView("radar");
$("themeToggle").onclick = () => { const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; localStorage.setItem("alfred-theme", next); };
const sidebarCollapsedKey = "horus-sidebar-collapsed";
function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem(sidebarCollapsedKey, collapsed ? "true" : "false");
  const button = $("sidebarCollapseButton");
  if (button) { button.textContent = collapsed ? "›" : "‹"; button.setAttribute("aria-label", collapsed ? "Expandir menu" : "Recolher menu"); }
}
if ($("sidebarCollapseButton")) $("sidebarCollapseButton").onclick = () => setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
setSidebarCollapsed(localStorage.getItem(sidebarCollapsedKey) === "true");
document.addEventListener("keydown", event => { const card = event.target.closest?.(".edital-item[data-open-edital]"); if (card && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openDrawer(card.dataset.openEdital); } });
if ($("logoutButton")) {
  $("logoutButton").onclick = async () => {
    try { await api("/logout", {method:"POST"}); } finally { window.location.assign("/login"); }
  };
}
document.documentElement.dataset.theme = localStorage.getItem("alfred-theme") || "light";
$("applyRadarFilters").onclick = applyFilters; $("clearRadarFilters").onclick = clearFilters; $("radarRefreshButton").onclick = applyFilters; $("radarSort").onchange = () => renderRadar();
$("refreshButton").onclick = loadEditais; $("refreshHistoryButton").onclick = history; $("searchButton").onclick = loadEditais; $("editaisSearch").onkeydown = event => { if (event.key === "Enter") { event.preventDefault(); loadEditais(); } }; let editaisSearchTimer; $("editaisSearch").oninput = () => { clearTimeout(editaisSearchTimer); editaisSearchTimer = setTimeout(loadEditais, 280); }; $("editaisSearch").closest(".search-field")?.addEventListener("click", () => $("editaisSearch").focus());
$("clearFavoritesButton").onclick = () => { favorites.clear(); saveFavorites(); renderRadar(); renderFavorites(); toast("Favoritos removidos"); };
$("closeDrawer").onclick = closeDrawer; $("drawerBackdrop").onclick = closeDrawer;
$("closeEditalModal").onclick = closeEditalModal; $("cancelEditalButton").onclick = closeEditalModal; $("editalModal").onclick = event => { if (event.target === $("editalModal")) closeEditalModal(); };
$("cancelDeleteEdital").onclick = closeDeleteEditalModal; $("confirmDeleteEdital").onclick = confirmDeleteEdital; $("deleteEditalModal").onclick = event => { if (event.target === $("deleteEditalModal")) closeDeleteEditalModal(); };
$("pipelineRefreshButton").onclick = loadPipeline; $("pipelineApplyFilters").onclick = loadPipeline; $("pipelineClearFilters").onclick = () => { $("pipelineSearch").value = ""; $("pipelineStageFilter").value = ""; $("pipelinePriorityFilter").value = ""; $("pipelineResponsibleFilter").value = ""; $("pipelineUfFilter").value = ""; $("pipelineUrgentFilter").checked = false; loadPipeline(); }; $("pipelineSearch").onkeydown = event => event.key === "Enter" && loadPipeline();
$("closePipelineModal").onclick = closePipelineModal; $("cancelPipelineButton").onclick = closePipelineModal; $("pipelineModal").onclick = event => { if (event.target === $("pipelineModal")) closePipelineModal(); };
$("closeChecklistModal").onclick = closeChecklistModal; $("checklistModal").onclick = event => { if (event.target === $("checklistModal")) closeChecklistModal(); };
$("generateChecklistButton").onclick = generateActiveChecklist; $("checklistStatusFilter").onchange = () => renderChecklist();
if ($("checklistSearchInput")) $("checklistSearchInput").oninput = () => renderChecklist();
document.querySelectorAll("[data-checklist-tab]").forEach(button => button.onclick = () => activateChecklistTab(button.dataset.checklistTab));

if ($("chooseWorkspaceFiles")) $("chooseWorkspaceFiles").onclick = () => $("workspaceFileInput").click();
if ($("workspaceFileInput")) $("workspaceFileInput").onchange = event => uploadWorkspaceFiles(event.target.files);
if ($("workspaceDropzone")) {
  const zone = $("workspaceDropzone");
  ["dragenter","dragover"].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add("dragging"); }));
  ["dragleave","drop"].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.remove("dragging"); }));
  zone.addEventListener("drop", event => uploadWorkspaceFiles(event.dataTransfer.files));
  zone.onclick = () => $("workspaceFileInput").click();
  zone.onkeydown = event => { if (event.key === "Enter" || event.key === " ") $("workspaceFileInput").click(); };
}
$("checklistDownloadButton").onclick = downloadActiveChecklistPdf;
$("checklistPrintReportButton").onclick = () => activeChecklistEditalId && generateReportForIds([activeChecklistEditalId], "Relatório Individual da Concorrência");
$("generateSelectedReportButton").onclick = () => generateReportForIds([...selectedEditais]);
$("monitorRunNowButton").onclick = runMonitorNow; $("monitorRefreshHistory").onclick = loadMonitorHistory;
$("monitorOpenReportButton").onclick = () => { const link = document.createElement("a"); link.href = "/api/monitor/report"; link.target = "_blank"; link.click(); };
if ($("refreshReportsButton")) $("refreshReportsButton").onclick = loadSavedReports;
if ($("openReportsFolderButton")) $("openReportsFolderButton").onclick = openReportsFolder;
if ($("deleteSelectedButton")) $("deleteSelectedButton").onclick = () => bulkDeleteEditais({ids:[...selectedEditais]});
if ($("deleteClosedButton")) $("deleteClosedButton").onclick = () => bulkDeleteEditais({deleteClosed:true});
if ($("reportsSearch")) $("reportsSearch").oninput = renderSavedReports;
if ($("reportsCategoryFilter")) $("reportsCategoryFilter").onchange = renderSavedReports;
if ($("notificationConfigForm")) $("notificationConfigForm").onsubmit = saveNotificationConfig;
if ($("segmentSettingsForm")) $("segmentSettingsForm").onsubmit = saveSegmentSettings;
if ($("notificationTestButton")) $("notificationTestButton").onclick = sendNotificationTest;
if ($("notificationRunNow")) $("notificationRunNow").onclick = runNotificationsNow;
if ($("notificationRefreshHistory")) $("notificationRefreshHistory").onclick = loadNotificationHistory;
$("commandButton").onclick = openCommand; $("commandSearch").oninput = event => commandResults(event.target.value); $("commandPalette").onclick = event => { if (event.target === $("commandPalette")) closeCommand(); };
document.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommand(); } if (event.key === "Escape") { closeCommand(); closeDrawer(); closeEditalModal(); closeDeleteEditalModal(); closePipelineModal(); closeChecklistModal(); } });

document.addEventListener("click", event => {
  const favorite = event.target.closest("[data-favorite]");
  if (favorite) { event.stopPropagation(); const id = favorite.dataset.favorite; favorites.has(id) ? favorites.delete(id) : favorites.add(id); saveFavorites(); renderRadar(); renderFavorites(); toast(favorites.has(id) ? "Oportunidade favoritada" : "Favorito removido"); return; }
  const edit = event.target.closest("[data-edit-edital]");
  if (edit) { event.stopPropagation(); openEditalModal(edit.dataset.editEdital); return; }
  const remove = event.target.closest("[data-delete-edital]");
  if (remove) { event.stopPropagation(); requestDeleteEdital(remove.dataset.deleteEdital); return; }
  const openChecklist = event.target.closest("[data-open-checklist]");
  if (openChecklist) { event.stopPropagation(); closeDrawer(); openChecklistModal(openChecklist.dataset.openChecklist); return; }
  const saveChecklist = event.target.closest("[data-save-checklist]");
  if (saveChecklist) {
    event.stopPropagation();
    const id = saveChecklist.dataset.saveChecklist;
    const responsibleUserId = document.querySelector(`[data-checklist-responsible="${CSS.escape(id)}"]`)?.value || null;
    const dueDate = document.querySelector(`[data-checklist-due-date="${CSS.escape(id)}"]`)?.value || null;
    const notes = document.querySelector(`[data-checklist-notes="${CSS.escape(id)}"]`)?.value.trim() || null;
    saveChecklistItem(id, {responsible_user_id:responsibleUserId, due_date:dueDate, notes});
    return;
  }
  const openMonitorReport = event.target.closest("[data-open-monitor-report]");
  if (openMonitorReport) { event.stopPropagation(); const link = document.createElement("a"); link.href = "/api/monitor/report"; link.target = "_blank"; link.click(); return; }
  const openSaved = event.target.closest("[data-open-saved-report]");
  if (openSaved) { event.stopPropagation(); openSavedReport(openSaved.dataset.openSavedReport); return; }
  const deleteSaved = event.target.closest("[data-delete-saved-report]");
  if (deleteSaved) { event.stopPropagation(); deleteSavedReport(deleteSaved.dataset.deleteSavedReport, deleteSaved.dataset.reportName || "relatório"); return; }
  const editUser = event.target.closest("[data-edit-user]"); if (editUser) { event.stopPropagation(); openUserModal(editUser.dataset.editUser); return; }
  const resetUser = event.target.closest("[data-reset-user-password]"); if (resetUser) { event.stopPropagation(); openPasswordResetModal(resetUser.dataset.resetUserPassword); return; }
  const toggleUser = event.target.closest("[data-toggle-user]"); if (toggleUser) { event.stopPropagation(); toggleUserStatus(toggleUser.dataset.toggleUser); return; }
  const openPipeline = event.target.closest("[data-open-pipeline]"); if (openPipeline) { event.stopPropagation(); closeDrawer(); switchView("pipeline"); openPipelineModal(openPipeline.dataset.openPipeline); return; }
  const open = event.target.closest("[data-open-edital]"); if (open) openDrawer(open.dataset.openEdital);
  const state = event.target.closest("[data-state]"); if (state) { switchView("radar"); $("radarUf").value = state.dataset.state; applyFilters(); }
  const mode = event.target.closest("[data-radar-mode]"); if (mode) { radarMode = mode.dataset.radarMode; localStorage.setItem("alfred-radar-mode", radarMode); document.querySelectorAll("[data-radar-mode]").forEach(button => button.classList.toggle("active", button.dataset.radarMode === radarMode)); renderRadar(); }
  const quick = event.target.closest("[data-quick]"); if (quick) { quickFilter = quickFilter === quick.dataset.quick ? null : quick.dataset.quick; document.querySelectorAll("[data-quick]").forEach(button => button.classList.toggle("active", button.dataset.quick === quickFilter)); renderRadar(); }
  const prompt = event.target.closest("[data-prompt]"); if (prompt) { $("question").value = prompt.dataset.prompt; $("question").focus(); }
  const analyze = event.target.closest("[data-analyze-edital]"); if (analyze) { closeDrawer(); selectedEditais.add(analyze.dataset.analyzeEdital); switchView("base"); const check = document.querySelector(`.edital-checkbox[value="${CSS.escape(analyze.dataset.analyzeEdital)}"]`); if (check) check.checked = true; selection(); switchView("analysis"); }
  const command = event.target.closest("[data-command-type]"); if (command) { closeCommand(); command.dataset.commandType === "view" ? switchView(command.dataset.commandId) : openDrawer(command.dataset.commandId); }
});

document.addEventListener("change", event => {
  const status = event.target.closest("[data-checklist-status]");
  if (status) {
    const id = status.dataset.checklistStatus;
    const responsibleUserId = document.querySelector(`[data-checklist-responsible="${CSS.escape(id)}"]`)?.value || null;
    const notes = document.querySelector(`[data-checklist-notes="${CSS.escape(id)}"]`)?.value.trim() || null;
    saveChecklistItem(id, {status:status.value,responsible_user_id:responsibleUserId,notes});
  }
});

function restoreInteractiveControls() {
  const ids = ["editaisSearch","radarSearch","radarUf","radarModality","radarStatus","pipelineSearch","pipelineStageFilter","pipelinePriorityFilter","pipelineResponsibleFilter","pipelineUfFilter","reportsSearch","reportsCategoryFilter","commandSearch","notificationTime","notificationBitrixWebhook","notificationSmtpHost","notificationSmtpPort","notificationSmtpUsername","notificationSmtpPassword","notificationSenderEmail","notificationSenderName","notificationTestUser"];
  ids.forEach(id => {
    const control = $(id);
    if (!control) return;
    control.removeAttribute("readonly");
    control.removeAttribute("inert");
    if (!control.dataset.permanentlyDisabled) control.disabled = false;
    control.style.pointerEvents = "auto";
  });
  document.querySelectorAll(".modal-overlay.hidden,.drawer-backdrop.hidden,.command-overlay.hidden").forEach(layer => {
    layer.style.pointerEvents = "none";
  });
  document.body.classList.add("horus-controls-ready");
}

["editaisSearch","radarSearch","pipelineSearch","pipelineResponsibleFilter"].forEach(id => {
  const input = $(id);
  if (!input) return;
  input.addEventListener("pointerdown", () => input.focus(), {passive:true});
});
["radarUf","radarModality","radarStatus","pipelineStageFilter","pipelinePriorityFilter","pipelineUfFilter"].forEach(id => {
  const select = $(id);
  if (!select) return;
  select.addEventListener("pointerdown", () => select.focus(), {passive:true});
});
restoreInteractiveControls();
populateUfs(cache);
populatePipelineUfs(pipelineCache);
document.querySelectorAll("[data-radar-mode]").forEach(button => button.classList.toggle("active", button.dataset.radarMode === radarMode));
$("pipelineForm").onsubmit = async event => {
  event.preventDefault();
  const id = $("pipelineEditalId").value;
  try {
    await api(`/api/editais/${id}/pipeline`, {method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
      stage: $("pipelineStage").value,
      priority: $("pipelinePriority").value,
      responsible_user_id: $("pipelineResponsible").value || null,
      internal_notes: $("pipelineNotes").value.trim() || null,
      change_note: $("pipelineChangeNote").value.trim() || null
    })});
    closePipelineModal();
    toast("Oportunidade atualizada");
    await Promise.all([loadEditais(), loadPipeline(), dashboard()]);
  } catch (error) { toast(error.message); }
};
$("editalForm").onsubmit = async event => {
  event.preventDefault();
  const id = $("editalId").value;
  try {
    await api(`/api/editais/${id}`, {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        title: $("editalTitle").value.trim(),
        organization: $("editalOrganization").value.trim() || null,
        uf: $("editalUf").value.trim() || null,
        municipality: $("editalMunicipality").value.trim() || null,
        modality_name: $("editalModality").value.trim() || null,
        status_name: $("editalStatus").value.trim() || null,
        estimated_value: $("editalValue").value ? Number($("editalValue").value) : null,
        proposal_end: $("editalProposalEnd").value ? new Date($("editalProposalEnd").value).toISOString() : null,
        object_text: $("editalObject").value.trim() || null
      })
    });
    closeEditalModal();
    toast("Edital atualizado com sucesso");
    await Promise.all([loadEditais(), dashboard()]);
    renderRadar();
    renderFavorites();
  } catch (error) {
    toast(error.message);
  }
};

if ($("newUserButton")) $("newUserButton").onclick = () => openUserModal();
if ($("usersSearch")) $("usersSearch").oninput = renderUsers;
if ($("closeUserModal")) $("closeUserModal").onclick = closeUserModal;
if ($("cancelUserButton")) $("cancelUserButton").onclick = closeUserModal;
if ($("userModal")) $("userModal").onclick = event => { if (event.target === $("userModal")) closeUserModal(); };
if ($("closePasswordResetModal")) $("closePasswordResetModal").onclick = closePasswordResetModal;
if ($("cancelPasswordReset")) $("cancelPasswordReset").onclick = closePasswordResetModal;
if ($("passwordResetModal")) $("passwordResetModal").onclick = event => { if (event.target === $("passwordResetModal")) closePasswordResetModal(); };
if ($("userForm")) $("userForm").onsubmit = async event => {
  event.preventDefault();
  const id = $("userId").value;
  const selectedPermissions = [...document.querySelectorAll('[name="userPermission"]:checked')].map(box => box.value);
  if (!selectedPermissions.length) { setStatus($("userFormStatus"), "Selecione ao menos um módulo para o usuário.", "error"); $("userFormStatus").classList.remove("hidden"); return; }
  const payload = {username:$("userUsername").value.trim(),email:$("userEmail").value.trim(),full_name:$("userFullName").value.trim(),department:$("userDepartment").value.trim(),phone_voip:$("userPhone").value.trim() || null,bitrix_user_id:$("userBitrixId").value.trim() || null,notify_email:$("userNotifyEmail").checked,notify_bitrix:$("userNotifyBitrix").checked,is_active:$("userActive").checked,permissions:selectedPermissions};
  if (!id) payload.password = $("userPassword").value;
  try {
    await api(id ? `/api/users/${id}` : "/api/users", {method:id ? "PUT" : "POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    closeUserModal(); toast(id ? "Usuário atualizado" : "Usuário criado"); await loadUsers();
  } catch (error) { setStatus($("userFormStatus"), error.message, "error"); $("userFormStatus").classList.remove("hidden"); }
};
if ($("passwordResetForm")) $("passwordResetForm").onsubmit = async event => {
  event.preventDefault();
  try { await api(`/api/users/${$("passwordResetUserId").value}/reset-password`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({password:$("passwordResetValue").value})}); closePasswordResetModal(); toast("Senha atualizada"); }
  catch (error) { toast(error.message); }
};

$("monitorForm").onsubmit = async event => {
  event.preventDefault();
  const [hour, minute] = $("monitorTime").value.split(":").map(Number);
  const modalities = [...document.querySelectorAll('[name="monitorModalidade"]:checked')].map(item => Number(item.value));
  if (!modalities.length) { toast("Selecione ao menos uma modalidade"); return; }
  try {
    const config = await api("/api/monitor/config", {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        enabled: $("monitorEnabled").checked,
        hour,
        minute,
        lookback_days: Number($("monitorLookback").value),
        modalities,
        uf: $("monitorUf").value.trim() || null,
        keywords: $("monitorKeywords").value.split(",").map(value => value.trim()).filter(Boolean),
        max_pages: Number($("monitorMaxPages").value),
        download_documents: $("monitorDownloadDocuments").checked,
        generate_report: $("monitorGenerateReport").checked
      })
    });
    fillMonitorForm(config);
    setStatus($("monitorStatusBox"), config.enabled ? "Monitoramento diário salvo e ativado." : "Configuração salva. O monitoramento está pausado.", "success");
    $("monitorStatusBox").classList.remove("hidden");
    toast("Monitoramento salvo");
  } catch (error) { setStatus($("monitorStatusBox"), error.message, "error"); $("monitorStatusBox").classList.remove("hidden"); }
};
$("syncForm").onsubmit = async event => { event.preventDefault(); try { const modalidades = [...document.querySelectorAll('[name="modalidade"]:checked')].map(item => +item.value); const palavras = $("palavras").value.split(",").map(item => item.trim()).filter(Boolean); setStatus($("jobStatus"), "Consultando PNCP e AMUNES / LicitaMunes..."); $("jobStatus").classList.remove("hidden"); const payload = {data_inicial:$("dataInicial").value, data_final:$("dataFinal").value, modalidades, palavras_chave:palavras, baixar_documentos:$("baixarDocumentos").checked, max_paginas:+$("maxPaginas").value, tamanho_pagina:+$("tamanhoPagina").value}; const results = await Promise.allSettled([api("/api/sync/pncp", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)}), api("/api/sync/amunes", {method:"POST"})]); const pncp = results[0], amunes = results[1]; if (pncp.status === "rejected" && amunes.status === "rejected") throw new Error(`PNCP: ${pncp.reason?.message || "falhou"}. AMUNES: ${amunes.reason?.message || "falhou"}.`); if (pncp.status === "fulfilled") { poll(pncp.value.id); setStatus($("jobStatus"), amunes.status === "fulfilled" ? "Varredura multifuente iniciada." : `PNCP iniciado. AMUNES indisponível: ${amunes.reason?.message || "erro"}`, amunes.status === "fulfilled" ? "success" : "warning"); } else { poll(amunes.value.id); setStatus($("jobStatus"), `AMUNES iniciado. PNCP indisponível: ${pncp.reason?.message || "erro"}`, "warning"); } toast("Varredura iniciada nas fontes disponíveis."); } catch (error) { setStatus($("jobStatus"), error.message, "error"); } };
$("cancelJobButton").onclick = () => activeJobId && api(`/api/jobs/${activeJobId}/cancel`, {method:"POST"});
$("uploadForm").onsubmit = async event => { event.preventDefault(); const form = new FormData(); form.append("title", $("uploadTitle").value); form.append("file", $("uploadFile").files[0]); try { setStatus($("uploadStatus"), "Processando..."); const result = await api("/api/upload", {method:"POST", body:form}); setStatus($("uploadStatus"), `Concluído: ${result.documents_indexed} documento(s), ${result.chunks_created} trecho(s).`, "success"); event.target.reset(); loadEditais(); dashboard(); } catch (error) { setStatus($("uploadStatus"), error.message, "error"); } };
$("askForm").onsubmit = async event => { event.preventDefault(); const ids = [...selectedEditais]; $("answerPanel").classList.remove("hidden"); $("answerText").textContent = "Analisando..."; try { const result = await api("/api/ask", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({pergunta:$("question").value, edital_ids:ids, top_k:10})}); $("answerText").textContent = result.answer; $("sourcesList").innerHTML = result.sources.map(source => `<div class="source-item"><div><strong>Fonte ${source.source_number} — ${esc(source.document_title)}</strong><p>${esc(source.excerpt)}</p></div></div>`).join(""); } catch (error) { $("answerText").textContent = error.message; } };

const now = new Date(), past = new Date(now); past.setFullYear(now.getFullYear() - 1); $("dataFinal").value = iso(now); $("dataInicial").value = iso(past);
updateFavoriteCounters();
health();
switchView(landingView);
if (hasAccess("dashboard")) dashboard();
if (["dashboard","base_editais","radar","pipeline","consultor","relatorios"].some(hasAccess)) loadEditais();
if (hasAccess("pipeline")) loadPipeline();
if (hasAccess("monitoramento")) loadMonitorConfig();
if (hasAccess("relatorios")) loadSavedReports();
if (hasAccess("historico")) history();
if (isAdministrator) { loadUsers(); loadNotificationConfig(); }


document.querySelectorAll("[data-base-status]").forEach(button => {
  button.addEventListener("click", async () => {
    baseStatusFilter = button.dataset.baseStatus || "open";
    document.querySelectorAll("[data-base-status]").forEach(item => item.classList.toggle("active", item === button));
    await loadEditais();
  });
});

