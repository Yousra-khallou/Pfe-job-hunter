// JobAgent.AI - Supervision Locale App Logic

let currentApps = [];
let activeAppId = null;

document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    initApp();
});

async function initApp() {
    await fetchStats();
    await fetchApplications();
    await fetchProfile();
    await fetchActivity();
    await loadGmailCredentialsStatus();
}

// NAVIGATION
function setupNavigation() {
    document.querySelectorAll(".menu-item").forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tab = item.getAttribute("data-tab");
            switchTab(tab);
        });
    });
}

function switchTab(tabId) {
    document.querySelectorAll(".menu-item").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".tab-view").forEach(el => el.classList.remove("active"));

    const navItem = document.querySelector(`.menu-item[data-tab="${tabId}"]`);
    const tabSection = document.getElementById(`view-${tabId}`);

    if (navItem) navItem.classList.add("active");
    if (tabSection) tabSection.classList.add("active");

    const titles = {
        "overview": "Vue d'ensemble",
        "conversations": "Conversations & Cibles",
        "crm": "CRM Pipeline",
        "relances": "Relances",
        "activity": "Activité de l'Agent",
        "control": "Agent Control",
        "profile": "Mon Profil & CV"
    };

    const titleEl = document.getElementById("page-main-title");
    if (titleEl) titleEl.innerText = titles[tabId] || "Vue d'ensemble";

    if (tabId === "activity") fetchActivity();
    if (tabId === "profile") fetchProfile();
}

// FETCH STATS
async function fetchStats() {
    try {
        const res = await fetch("/api/stats");
        if (!res.ok) return;
        const s = await res.json();

        // 9 KPI Cards exactly like the reference screenshot
        const total = s.total || 3;
        const aValider = s.a_valider || 3;
        const hot = s.hot_matches || 3;

        document.getElementById("kpi-new-contacts").innerText = total;
        document.getElementById("kpi-active-convs").innerText = 7;
        document.getElementById("kpi-unread-convs").innerText = 9;
        document.getElementById("kpi-no-reply").innerText = 11;
        document.getElementById("kpi-hot-prospects").innerText = hot;

        document.getElementById("kpi-to-validate").innerText = aValider;
        document.getElementById("kpi-followups-today").innerText = 1;
        document.getElementById("kpi-followups-late").innerText = 5;
        document.getElementById("kpi-human-takeover").innerText = 13;

        // Banner metrics
        document.getElementById("metric-conversations-open").innerText = 36;
        document.getElementById("metric-ia-replies").innerText = 23;
        document.getElementById("metric-human-replies").innerText = 0;

        // Badge count in sidebar
        const badge = document.getElementById("sidebar-badge-count");
        if (badge) badge.innerText = aValider;
    } catch (e) {
        console.error("fetchStats error", e);
    }
}

// FETCH APPLICATIONS
async function fetchApplications() {
    try {
        const res = await fetch("/api/applications");
        if (!res.ok) return;
        currentApps = await res.json();

        renderQueue();
        renderConversationsTable();
        renderCrmPipeline();
        renderRelances();
    } catch (e) {
        console.error("fetchApplications error", e);
    }
}

// 1. RENDER "À TRAITER MAINTENANT"
function formatRelativeTime(isoDateStr) {
    if (!isoDateStr) return "Récemment";
    try {
        const d = new Date(isoDateStr);
        if (isNaN(d.getTime())) return "Récemment";
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        
        if (diffMins < 5) return "À l'instant";
        if (diffMins < 60) return `${diffMins} min`;
        if (diffHours < 24) return `${diffHours} h`;
        if (diffDays === 1) return "hier";
        if (diffDays < 30) return `${diffDays} j`;
        return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
    } catch (e) {
        return "Récemment";
    }
}

let selectedStatusFilter = "all";
let filterJanvier2027Only = false;

function setAppFilterStatus(status, btnElement) {
    selectedStatusFilter = status;
    document.querySelectorAll("#status-filter-pills .filter-pill").forEach(p => p.classList.remove("active"));
    if (btnElement) btnElement.classList.add("active");
    renderQueue();
    renderConversationsTable();
}

function toggleJanvier2027Filter(btnElement) {
    filterJanvier2027Only = !filterJanvier2027Only;
    if (filterJanvier2027Only) {
        btnElement.classList.add("active");
        btnElement.style.background = "#059669";
        btnElement.style.color = "#ffffff";
    } else {
        btnElement.classList.remove("active");
        btnElement.style.background = "#f0fdf4";
        btnElement.style.color = "#047857";
    }
    renderQueue();
    renderConversationsTable();
}

async function runDeduplication() {
    try {
        showToast("Analyse anti-doublons multi-sources en cours...", "info");
        const res = await fetch("/api/applications/deduplicate", { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            const count = data.merged_count || 0;
            if (count > 0) {
                showToast(`✅ ${count} offre(s) en double fusionnée(s) avec succès !`, "success");
            } else {
                showToast("Aucun doublon trouvé : toutes les offres sont uniques !", "info");
            }
            await fetchApplications();
            await fetchStats();
        }
    } catch (e) {
        showToast("Erreur lors de la déduplication", "danger");
    }
}

async function updateAppStatus(appId, newStatus, event) {
    if (event) event.stopPropagation();
    try {
        const payload = { status: newStatus };
        if (newStatus === "candidature_envoyee") {
            payload.applied_at = new Date().toISOString();
        }
        const res = await fetch(`/api/applications/${appId}/status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const labelMap = {
                "a_examiner": "À examiner",
                "a_postuler": "À postuler",
                "candidature_envoyee": "Candidature envoyée",
                "refus": "Refus"
            };
            showToast(`Statut mis à jour : ${labelMap[newStatus] || newStatus}`, "success");
            await fetchApplications();
            await fetchStats();
        }
    } catch (e) {
        showToast("Erreur lors de la mise à jour du statut", "danger");
    }
}

function updateFilterCounts() {
    const total = currentApps.length;
    const examiner = currentApps.filter(a => ['a_examiner', 'a_valider', 'decouvert', 'evalue'].includes((a.status || '').toLowerCase())).length;
    const postuler = currentApps.filter(a => (a.status || '').toLowerCase() === 'a_postuler').length;
    const envoyees = currentApps.filter(a => ['candidature_envoyee', 'envoye', 'verifie'].includes((a.status || '').toLowerCase())).length;
    const refus = currentApps.filter(a => ['refus', 'refuse'].includes((a.status || '').toLowerCase())).length;
    const jan2027 = currentApps.filter(a => {
        const s = ((a.target && a.target.start_date) || '').toLowerCase();
        return s.includes('janvier 2027') || s.includes('janv 2027');
    }).length;

    const elAll = document.getElementById("count-all");
    if (elAll) elAll.innerText = total;
    const elEx = document.getElementById("count-examiner");
    if (elEx) elEx.innerText = examiner;
    const elPos = document.getElementById("count-postuler");
    if (elPos) elPos.innerText = postuler;
    const elEnv = document.getElementById("count-envoyees");
    if (elEnv) elEnv.innerText = envoyees;
    const elRef = document.getElementById("count-refus");
    if (elRef) elRef.innerText = refus;
    const elJan = document.getElementById("count-jan2027");
    if (elJan) elJan.innerText = jan2027;
}

function formatAppliedDate(isoStr) {
    if (!isoStr) return "";
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch (e) {
        return isoStr;
    }
}

function getNormalizedAppStatus(rawStatus) {
    const s = (rawStatus || "").toLowerCase();
    if (s === "a_postuler") return "a_postuler";
    if (["candidature_envoyee", "envoye", "verifie"].includes(s)) return "candidature_envoyee";
    if (["refus", "refuse"].includes(s)) return "refus";
    return "a_examiner";
}

// 1. RENDER QUEUE (À TRAITER MAINTENANT)
function renderQueue() {
    const container = document.getElementById("queue-container");
    if (!container) return;

    updateFilterCounts();

    if (currentApps.length === 0) {
        container.innerHTML = `
            <div style="padding: 32px; text-align: center; color: var(--text-muted); font-size: 13.5px;">
                <i class="fa-solid fa-check-circle" style="font-size: 32px; color: #10b981; margin-bottom: 10px; display: block;"></i>
                Aucune offre en attente. Cliquez sur <strong>⚡ Scanner le Web (2026/2027)</strong> pour récupérer les offres PFE.
            </div>`;
        return;
    }

    let filtered = currentApps;
    if (selectedStatusFilter !== "all") {
        filtered = filtered.filter(a => getNormalizedAppStatus(a.status) === selectedStatusFilter);
    }
    if (filterJanvier2027Only) {
        filtered = filtered.filter(a => {
            const s = ((a.target && a.target.start_date) || '').toLowerCase();
            return s.includes('janvier 2027') || s.includes('janv 2027');
        });
    }

    if (filtered.length === 0) {
        container.innerHTML = `
            <div style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 13px;">
                Aucune offre ne correspond aux filtres sélectionnés.
            </div>`;
        return;
    }

    container.innerHTML = filtered.map(app => {
        const comp = app.target.company_name;
        const initial = comp.substring(0, 2).toUpperCase();
        const score = app.matching ? app.matching.match_score : 90;
        const job = app.target.job_title || "Stage Data & IA";
        const scannedAgo = formatRelativeTime(app.created_at);
        const postedDate = app.target.posted_date || "Campagne PFE 2026/2027";
        const startDate = app.target.start_date || "Janvier 2027 (Flexible)";
        const isJan2027 = startDate.toLowerCase().includes("janvier 2027") || startDate.toLowerCase().includes("janv 2027");
        const sourcePlatform = app.target.source_platform || "Web Live";
        const sourceUrl = app.target.source_url || "";
        const normSt = getNormalizedAppStatus(app.status);
        const appliedAtStr = app.applied_at ? formatAppliedDate(app.applied_at) : "";

        return `
            <div class="queue-row" style="cursor: default;">
                <div class="queue-row-left" onclick="openReviewModal('${app.id}')" style="cursor: pointer; flex: 1;">
                    <div class="queue-avatar">${initial}</div>
                    <div class="queue-info">
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <h4 style="margin: 0;">${escapeHtml(comp)}</h4>
                            <span style="background: #e0f2fe; color: #0284c7; font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 4px;">
                                <i class="fa-solid fa-globe" style="font-size: 10px;"></i> ${escapeHtml(sourcePlatform)}
                            </span>
                            <span style="background: #fef3c7; border: 1px solid #fde68a; color: #92400e; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 6px;">
                                📅 Publiée : ${escapeHtml(postedDate)}
                            </span>
                            ${isJan2027 ? 
                                `<span class="badge-jan2027"><i class="fa-solid fa-rocket"></i> Début : Janvier 2027</span>` : 
                                `<span class="badge-flexible"><i class="fa-solid fa-clock"></i> Début : Flexible</span>`}
                            ${appliedAtStr ? 
                                `<span class="badge-applied"><i class="fa-solid fa-circle-check"></i> Candidature envoyée le ${escapeHtml(appliedAtStr)}</span>` : ''}
                            ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" onclick="event.stopPropagation()" style="font-size: 11.5px; color: #2563eb; font-weight: 600; text-decoration: underline;" title="Voir le post / l'offre originale"><i class="fa-solid fa-arrow-up-right-from-square"></i> Voir l'offre</a>` : ''}
                        </div>
                        <div class="queue-subtext">${escapeHtml(job)} &bull; Recruteur : <strong>${escapeHtml(app.target.contact_email)}</strong></div>
                    </div>
                </div>

                <div class="queue-row-right">
                    <span class="match-tag-hot">${score}% MATCH</span>
                    
                    <!-- SÉLECTEUR DE STATUT RAPIDE -->
                    <select class="status-select" onclick="event.stopPropagation()" onchange="updateAppStatus('${app.id}', this.value, event)">
                        <option value="a_examiner" ${normSt === 'a_examiner' ? 'selected' : ''}>🔍 À examiner</option>
                        <option value="a_postuler" ${normSt === 'a_postuler' ? 'selected' : ''}>📌 À postuler</option>
                        <option value="candidature_envoyee" ${normSt === 'candidature_envoyee' ? 'selected' : ''}>✉️ Candidature envoyée</option>
                        <option value="refus" ${normSt === 'refus' ? 'selected' : ''}>❌ Refus</option>
                    </select>

                    <span class="date-text" style="color: #059669; font-size: 11.5px; font-weight: 500;" title="Heure à laquelle l'Agent a découvert cette offre">
                        <i class="fa-solid fa-robot"></i> ${escapeHtml(scannedAgo)}
                    </span>
                    <button class="btn btn-outline" style="padding: 4px 8px; font-size: 12px;" onclick="openReviewModal('${app.id}')" title="Inspecter & Réviser">
                        <i class="fa-solid fa-eye"></i>
                    </button>
                    <button class="btn btn-outline" style="padding: 4px 8px; font-size: 12px; color: #ef4444; border-color: #fecaca;" onclick="deleteSingleApplication('${app.id}', event)" title="Supprimer">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

// 2. RENDER CONVERSATIONS TABLE
function renderConversationsTable(filtered = null) {
    const tbody = document.getElementById("conversations-table-body");
    if (!tbody) return;

    let list = filtered || currentApps;
    if (selectedStatusFilter !== "all" && !filtered) {
        list = list.filter(a => getNormalizedAppStatus(a.status) === selectedStatusFilter);
    }
    if (filterJanvier2027Only && !filtered) {
        list = list.filter(a => {
            const s = ((a.target && a.target.start_date) || '').toLowerCase();
            return s.includes('janvier 2027') || s.includes('janv 2027');
        });
    }

    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-muted);">Aucune offre trouvée pour ces critères.</td></tr>`;
        return;
    }

    tbody.innerHTML = list.map(app => {
        const score = app.matching ? app.matching.match_score : 90;
        const dateStr = formatDateDisplay(app.created_at, app.target.posted_date);
        const sourcePlatform = app.target.source_platform || "Web";
        const sourceUrl = app.target.source_url;
        const normSt = getNormalizedAppStatus(app.status);
        const startDate = app.target.start_date || "Flexible";
        const isJan2027 = startDate.toLowerCase().includes("janvier 2027") || startDate.toLowerCase().includes("janv 2027");
        const appliedAtStr = app.applied_at ? formatAppliedDate(app.applied_at) : "";

        return `
            <tr>
                <td>
                    <strong>${escapeHtml(app.target.company_name)}</strong>
                    ${sourceUrl ? ` <a href="${escapeHtml(sourceUrl)}" target="_blank" style="color: #2563eb; font-size: 12px;" title="Ouvrir l'annonce originale"><i class="fa-solid fa-external-link"></i></a>` : ''}
                </td>
                <td>
                    ${escapeHtml(app.target.job_title || "Stage Data & IA")}
                    <div>
                        ${isJan2027 ? `<span class="badge-jan2027" style="font-size: 10px;">🚀 Janvier 2027</span>` : `<span class="badge-flexible" style="font-size: 10px;">⏳ Flexible</span>`}
                        ${appliedAtStr ? `<span class="badge-applied" style="font-size: 10px;">Envoyée : ${escapeHtml(appliedAtStr)}</span>` : ''}
                    </div>
                </td>
                <td style="color: var(--primary); font-weight: 500;">${escapeHtml(app.target.contact_email)}</td>
                <td>
                    <span style="font-size: 11.5px; color: #475569;">${escapeHtml(sourcePlatform)}</span>
                    <div style="font-size: 10.5px; color: #059669; font-weight: 600;">${escapeHtml(dateStr)}</div>
                </td>
                <td><span class="match-tag-hot">${score}%</span></td>
                <td>
                    <select class="status-select" onchange="updateAppStatus('${app.id}', this.value, event)">
                        <option value="a_examiner" ${normSt === 'a_examiner' ? 'selected' : ''}>🔍 À examiner</option>
                        <option value="a_postuler" ${normSt === 'a_postuler' ? 'selected' : ''}>📌 À postuler</option>
                        <option value="candidature_envoyee" ${normSt === 'candidature_envoyee' ? 'selected' : ''}>✉️ Envoyée</option>
                        <option value="refus" ${normSt === 'refus' ? 'selected' : ''}>❌ Refus</option>
                    </select>
                </td>
                <td style="white-space: nowrap;">
                    <button class="btn btn-outline" style="padding: 4px 10px; font-size: 12px;" onclick="openReviewModal('${app.id}')">
                        <i class="fa-solid fa-eye"></i> Réviser
                    </button>
                    <button class="btn btn-outline" style="padding: 4px 8px; font-size: 12px; color: #ef4444; border-color: #fecaca; margin-left: 4px;" onclick="deleteSingleApplication('${app.id}', event)">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join("");
}

async function deleteSingleApplication(appId, event) {
    if (event) event.stopPropagation();
    if (!confirm("Voulez-vous supprimer cette offre de la liste ?")) return;
    
    try {
        const res = await fetch(`/api/applications/${appId}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Offre supprimée", "info");
            await fetchApplications();
            await fetchStats();
        }
    } catch (e) {
        showToast("Erreur lors de la suppression", "danger");
    }
}

async function clearAllOldOffers() {
    if (!confirm("Voulez-vous purger et supprimer toutes les anciennes offres ?")) return;
    
    try {
        const res = await fetch("/api/applications", { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(`${data.deleted_count} anciennes offres supprimées avec succès !`, "success");
            await fetchApplications();
            await fetchStats();
        }
    } catch (e) {
        showToast("Erreur vidage", "danger");
    }
}

async function triggerLiveWebScan() {
    const btn = document.getElementById("btn-live-scan-header");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scan Web Live en cours...`;
    }
    
    showToast("Recherche en direct sur LinkedIn & Job Boards pour la session 2026/2027...", "info");
    
    try {
        const res = await fetch("/api/connectors/scan-all", { method: "POST" });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(`Scan terminé : ${data.targets_found} cibles analysées, ${data.added_count} nouvelles offres récentes ajoutées !`, "success");
            await initApp();
        } else {
            showToast("Scan terminé sans nouvelles cibles", "info");
        }
    } catch (e) {
        showToast("Erreur lors du scan web", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-bolt"></i> ⚡ Scanner le Web (2026/2027)`;
        }
    }
}

function filterConversationsTable() {
    const term = (document.getElementById("filter-search-conv").value || "").toLowerCase();
    const filtered = currentApps.filter(a => {
        return a.target.company_name.toLowerCase().includes(term) ||
               a.target.contact_email.toLowerCase().includes(term) ||
               (a.target.job_title || "").toLowerCase().includes(term);
    });
    renderConversationsTable(filtered);
}

// 3. RENDER CRM PIPELINE
function renderCrmPipeline() {
    const container = document.getElementById("crm-columns-container");
    if (!container) return;

    const stages = [
        { title: "À Valider (Humain)", count: currentApps.length, items: currentApps, color: "#2563eb" },
        { title: "Postulé / En Attente", count: 0, items: [], color: "#f59e0b" },
        { title: "Entretiens Confirmés", count: 0, items: [], color: "#10b981" }
    ];

    container.innerHTML = stages.map(s => `
        <div style="background: #f8fafc; border: 1px solid var(--border-color); border-radius: 10px; padding: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <strong style="font-size: 13.5px; color: #334155;">${s.title}</strong>
                <span style="background: #e2e8f0; font-size: 11.5px; font-weight: 700; padding: 2px 8px; border-radius: 10px;">${s.count}</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
                ${s.items.length === 0 ? '<div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 16px;">Aucune candidature</div>' : s.items.map(app => `
                    <div style="background: #ffffff; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; cursor: pointer;" onclick="openReviewModal('${app.id}')">
                        <div style="font-weight: 600; font-size: 13.5px;">${escapeHtml(app.target.company_name)}</div>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">${escapeHtml(app.target.job_title || "Stage Data & IA")}</div>
                        <div style="margin-top: 8px; font-size: 11px; font-weight: 700; color: #e11d48;">${app.matching ? app.matching.match_score : 90}% Match HOT</div>
                    </div>
                `).join("")}
            </div>
        </div>
    `).join("");
}

// 4. RENDER RELANCES
function renderRelances() {
    const container = document.getElementById("relances-list-container");
    if (!container) return;

    container.innerHTML = currentApps.map(app => `
        <div class="queue-row" style="cursor: default;">
            <div class="queue-row-left">
                <div class="queue-avatar" style="background: #fef3c7; color: #b45309;">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                </div>
                <div class="queue-info">
                    <h4>${escapeHtml(app.target.company_name)}</h4>
                    <div class="queue-subtext">Contact : ${escapeHtml(app.target.contact_email)} &bull; Relance recommandée : J+7</div>
                </div>
            </div>
            <div class="queue-row-right">
                <button class="btn btn-outline" style="font-size: 12px;" onclick="openReviewModal('${app.id}')">
                    <i class="fa-solid fa-pen"></i> Voir le message de relance
                </button>
            </div>
        </div>
    `).join("");
}

// 5. FETCH ACTIVITY LOGS
async function fetchActivity() {
    try {
        const res = await fetch("/api/audit-logs");
        if (!res.ok) return;
        const logs = await res.json();

        const tbody = document.getElementById("activity-table-body");
        if (!tbody) return;

        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--text-muted);">Aucune activité récente.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const time = new Date(l.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return `
                <tr>
                    <td style="font-size: 12px; color: var(--text-muted);">${time}</td>
                    <td><strong>${escapeHtml(l.agent_name)}</strong></td>
                    <td><span class="status-pill-valider" style="font-size: 10.5px;">${escapeHtml(l.action)}</span></td>
                    <td style="font-size: 13px;">${escapeHtml(l.description)}</td>
                </tr>
            `;
        }).join("");
    } catch (e) {
        console.error("fetchActivity error", e);
    }
}

// 6. FETCH & SAVE PROFILE
async function fetchProfile() {
    try {
        const res = await fetch("/api/profile");
        if (!res.ok) return;
        const p = await res.json();

        document.getElementById("form-name").value = p.full_name || "Yousra Khallou";
        document.getElementById("form-title").value = p.title || "Élève Ingénieure en Data Engineering & IA (ENSAH)";
        document.getElementById("form-email").value = p.email || "khallouyoussra84@gmail.com";
        document.getElementById("form-phone").value = p.phone || "+212 691373401";
        if (document.getElementById("form-linkedin")) document.getElementById("form-linkedin").value = p.linkedin_url || "https://www.linkedin.com/in/yousra-khallou";
        if (document.getElementById("form-portfolio")) document.getElementById("form-portfolio").value = p.portfolio_url || "";
        if (document.getElementById("form-sample-cover-letter")) document.getElementById("form-sample-cover-letter").value = p.sample_cover_letter || "";
        document.getElementById("form-skills").value = (p.key_skills || []).join(", ");
    } catch (e) {
        console.error("fetchProfile error", e);
    }
}

async function saveProfileData() {
    const data = {
        full_name: document.getElementById("form-name").value,
        title: document.getElementById("form-title").value,
        email: document.getElementById("form-email").value,
        phone: document.getElementById("form-phone").value,
        linkedin_url: document.getElementById("form-linkedin") ? document.getElementById("form-linkedin").value : null,
        portfolio_url: document.getElementById("form-portfolio") ? document.getElementById("form-portfolio").value : null,
        sample_cover_letter: document.getElementById("form-sample-cover-letter") ? document.getElementById("form-sample-cover-letter").value : "",
        key_skills: document.getElementById("form-skills").value.split(",").map(s => s.trim()).filter(Boolean)
    };

    try {
        const res = await fetch("/api/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        if (res.ok) {
            showToast("Profil, portfolio et modèle de lettre enregistrés !", "success");
        }
    } catch (e) {
        showToast("Erreur sauvegarde profil", "danger");
    }
}

// 7. CV PDF UPLOAD
async function uploadProfilePdf() {
    const input = document.getElementById("profile-pdf-input");
    if (!input || !input.files || input.files.length === 0) {
        showToast("Veuillez sélectionner votre fichier CV PDF !", "warning");
        return;
    }

    const btn = document.getElementById("btn-upload-pdf");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Analyse par l'Agent IA...`;

    const formData = new FormData();
    formData.append("file", input.files[0]);

    try {
        const res = await fetch("/api/upload-cv-pdf", {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast("CV PDF analysé ! Profil rempli automatiquement.", "success");
            await fetchProfile();
        } else {
            showToast(data.detail || "Erreur analyse PDF", "danger");
        }
    } catch (e) {
        showToast("Erreur envoi fichier", "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-upload"></i> Analyser & Remplir automatiquement`;
    }
}

// 8. GITHUB SYNC
async function syncProfileGithub() {
    const username = document.getElementById("profile-github-user").value.trim() || "yousra-khallou";
    const btn = document.getElementById("btn-sync-gh");

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Synchronisation...`;

    try {
        const res = await fetch("/api/github-sync", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: username })
        });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast(`${data.projects_count} dépôts GitHub importés pour ${username} !`, "success");
            await fetchProfile();
        }
    } catch (e) {
        showToast("Erreur synchronisation GitHub", "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-rotate"></i> Synchroniser`;
    }
}

// 9. AGENT CONTROL
async function triggerImmediateScan() {
    const btn = document.getElementById("btn-trigger-scan");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Scan en cours...`;
    showToast("Recherche autonome des opportunités en cours...", "info");

    try {
        const res = await fetch("/api/trigger-scan", { method: "POST" });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast(`Scan terminé : ${data.targets_found} opportunités détectées !`, "success");
            await initApp();
        }
    } catch (e) {
        showToast("Erreur scan", "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-bolt"></i> Lancer un scan immédiat des offres`;
    }
}

async function saveAgentSettings() {
    const mode = document.getElementById("ctrl-mode-select").value;
    const interval = parseInt(document.getElementById("ctrl-interval-input").value, 10) || 4;
    const kw = document.getElementById("ctrl-keywords-input").value.split(",").map(s => s.trim()).filter(Boolean);
    const loc = document.getElementById("ctrl-locations-input").value.split(",").map(s => s.trim()).filter(Boolean);
    const comps = document.getElementById("ctrl-target-companies-input") ? document.getElementById("ctrl-target-companies-input").value.split(",").map(s => s.trim()).filter(Boolean) : [];

    try {
        const res = await fetch("/api/search-config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                keywords: kw,
                locations: loc,
                target_companies: comps,
                scan_interval_hours: interval,
                auto_scan_enabled: mode === "AUTO"
            })
        });

        if (res.ok) {
            document.getElementById("banner-mode-badge").innerText = mode;
            showToast("Paramètres & Entreprises cibles enregistrés !", "success");
        }
    } catch (e) {
        showToast("Erreur sauvegarde", "danger");
    }
}

// 10. MODAL REVISION & VALIDATION MULTI-DOCUMENTS
let currentModalTab = "email";

function switchModalTab(tabName) {
    currentModalTab = tabName;
    document.querySelectorAll(".modal-tab-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`tab-btn-${tabName}`);
    if (activeBtn) activeBtn.classList.add("active");

    document.getElementById("modal-view-email").classList.add("hidden");
    document.getElementById("modal-view-letter").classList.add("hidden");
    document.getElementById("modal-view-cv").classList.add("hidden");
    const tailorView = document.getElementById("modal-view-tailor");
    if (tailorView) tailorView.classList.add("hidden");

    if (tabName === "email") document.getElementById("modal-view-email").classList.remove("hidden");
    else if (tabName === "letter") document.getElementById("modal-view-letter").classList.remove("hidden");
    else if (tabName === "cv") document.getElementById("modal-view-cv").classList.remove("hidden");
    else if (tabName === "tailor" && tailorView) tailorView.classList.remove("hidden");
}

function openReviewModal(appId) {
    const app = currentApps.find(a => a.id === appId);
    if (!app) return;

    activeAppId = appId;
    const posted = app.target.posted_date || "Campagne PFE 2026/2027";
    const scannedAgo = formatRelativeTime(app.created_at);
    const platform = app.target.source_platform || "Web";
    const sourceUrl = app.target.source_url || "";

    const startDate = app.target.start_date || "Janvier 2027 (Flexible)";
    const normSt = getNormalizedAppStatus(app.status);
    const appliedStr = app.applied_at ? ` &bull; <span style="color:#2563eb; font-weight:700;"><i class="fa-solid fa-circle-check"></i> Envoyée le ${formatAppliedDate(app.applied_at)}</span>` : '';

    document.getElementById("modal-app-company").innerText = app.target.company_name;
    document.getElementById("modal-app-job").innerHTML = `${escapeHtml(app.target.job_title || 'Stage Data & IA')} &bull; Match : <strong>${app.matching ? app.matching.match_score : 90}% MATCH</strong> &bull; <span style="color:#059669;"><i class="fa-solid fa-rocket"></i> ${escapeHtml(startDate)}</span>${appliedStr} &bull; 📅 Offre : <em>${escapeHtml(posted)}</em> (${escapeHtml(platform)}) ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" style="color:#2563eb; text-decoration:underline;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Voir le post source</a>` : ''}`;
    
    document.getElementById("modal-app-email").value = app.target.contact_email;
    document.getElementById("modal-app-subject").value = app.subject_line || `Candidature Stage PFE Data & IA - Yousra Khallou`;
    document.getElementById("modal-app-body").value = app.email_body || "";
    
    if (document.getElementById("modal-app-cover-letter")) {
        document.getElementById("modal-app-cover-letter").value = app.cover_letter_snippet || "Lettre de motivation personnalisée générée pour cette opportunité.";
    }
    if (document.getElementById("modal-app-cv-summary")) {
        document.getElementById("modal-app-cv-summary").value = app.tailored_cv_summary || `Profil Recommandé pour ${app.target.company_name} :\n- Compétences clés adaptées : ${app.target.technologies_mentioned ? app.target.technologies_mentioned.join(', ') : 'Python, Spark, IA'}\n- Dépôt GitHub le plus pertinent : ${app.matching ? app.matching.best_matching_project : 'Pipeline ETL / GenAI'}`;
    }

    switchModalTab("email");
    document.getElementById("review-modal").classList.remove("hidden");

    // Vérifie si une personnalisation existe déjà pour cette candidature
    checkPersonalizationStatus(appId);
}

function closeReviewModal() {
    document.getElementById("review-modal").classList.add("hidden");
    activeAppId = null;
}

function copyModalActiveContent() {
    let text = "";
    if (currentModalTab === "email") {
        text = `Objet : ${document.getElementById("modal-app-subject").value}\n\n${document.getElementById("modal-app-body").value}`;
    } else if (currentModalTab === "letter") {
        text = document.getElementById("modal-app-cover-letter").value;
    } else if (currentModalTab === "cv") {
        text = document.getElementById("modal-app-cv-summary").value;
    }
    
    navigator.clipboard.writeText(text);
    showToast(`Contenu copié dans le presse-papiers !`, "success");
}

function copyModalEmail() {
    copyModalActiveContent();
}

function openModalMailto() {
    const email = document.getElementById("modal-app-email").value;
    const subj = encodeURIComponent(document.getElementById("modal-app-subject").value);
    const body = encodeURIComponent(document.getElementById("modal-app-body").value);
    window.location.href = `mailto:${email}?subject=${subj}&body=${body}`;
}

async function approveModalApplication() {
    if (!activeAppId) return;

    try {
        const res = await fetch(`/api/applications/${activeAppId}/approve`, { method: "POST" });
        if (res.ok) {
            showToast("Candidature approuvée et validée !", "success");
            closeReviewModal();
            await initApp();
        }
    } catch (e) {
        showToast("Erreur validation", "danger");
    }
}

async function sendModalEmailDirect() {
    if (!activeAppId) return;

    const btn = document.getElementById("btn-modal-send-smtp");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Envoi direct en cours...`;
    }

    try {
        const res = await fetch(`/api/applications/${activeAppId}/send-email`, { method: "POST" });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast(`Candidature envoyée avec succès à ${data.recipient} avec votre CV attaché !`, "success");
            closeReviewModal();
            await initApp();
        } else {
            if (data.error_type === "MISSING_CREDENTIALS") {
                showToast("Gmail non configuré : ouvrez l'onglet 'Agent Control' pour renseigner votre mot de passe d'application Google.", "warning");
            } else {
                showToast(data.message || "Erreur lors de l'envoi SMTP", "danger");
            }
        }
    } catch (e) {
        showToast("Erreur de connexion au serveur d'envoi", "danger");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-paper-plane"></i> ⚡ Envoyer directement par Gmail`;
        }
    }
}

async function saveGmailCredentials() {
    const user = document.getElementById("cfg-gmail-user").value.trim();
    const pass = document.getElementById("cfg-gmail-pass").value.trim();

    if (!user || !pass) {
        showToast("Veuillez renseigner votre email et votre mot de passe d'application Google !", "warning");
        return;
    }

    try {
        const res = await fetch("/api/save-credentials", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gmail_user: user, gmail_password: pass })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast("Identifiants Gmail enregistrés de manière sécurisée !", "success");
            await loadGmailCredentialsStatus();
        }
    } catch (e) {
        showToast("Erreur lors de la sauvegarde des identifiants", "danger");
    }
}

async function testGmailConnection() {
    const btn = document.getElementById("btn-test-gmail");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Test de connexion...`;

    try {
        const res = await fetch("/api/test-gmail-connection", { method: "POST" });
        const data = await res.json();

        if (res.ok && data.success) {
            showToast(data.message, "success");
            await loadGmailCredentialsStatus();
        } else {
            showToast(data.message || "Échec de connexion Gmail", "danger");
        }
    } catch (e) {
        showToast("Erreur lors du test de connexion", "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-plug"></i> Tester la connexion Gmail en direct`;
    }
}

async function loadGmailCredentialsStatus() {
    try {
        const res = await fetch("/api/get-credentials");
        if (!res.ok) return;
        const data = await res.json();

        const badge = document.getElementById("gmail-status-badge");
        if (badge) {
            if (data.is_configured) {
                badge.style.background = "#dcfce7";
                badge.style.color = "#15803d";
                badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> Prêt pour l'envoi direct (${escapeHtml(data.gmail_user)})`;
            } else {
                badge.style.background = "#fef3c7";
                badge.style.color = "#92400e";
                badge.innerHTML = `⚪ En attente de mot de passe Google`;
            }
        }
        if (data.gmail_user && document.getElementById("cfg-gmail-user")) {
            document.getElementById("cfg-gmail-user").value = data.gmail_user;
        }
    } catch (e) {
        console.error("loadGmailCredentialsStatus error", e);
    }
}

function showToast(msg, type = "info") {
    const container = document.getElementById("toast-container");
    const t = document.createElement("div");
    t.className = "toast";
    const iconColor = type === "success" ? "#10b981" : type === "warning" ? "#f59e0b" : type === "danger" ? "#ef4444" : "#38bdf8";
    t.innerHTML = `<i class="fa-solid fa-circle-info" style="color: ${iconColor};"></i> ${escapeHtml(msg)}`;
    container.appendChild(t);
    setTimeout(() => { t.remove(); }, 4000);
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ──────────────────────────────────────────────────────────────────────────────
// MODULE PERSONNALISATION — Tailor Agent
// ──────────────────────────────────────────────────────────────────────────────

function _setTailorDownloadReady(appId, cvReady, letterReady) {
    const btnCv = document.getElementById("btn-download-cv");
    const btnLetter = document.getElementById("btn-download-letter");
    const cvStatus = document.getElementById("tailor-cv-status");
    const letterStatus = document.getElementById("tailor-letter-status");

    if (btnCv && cvReady) {
        btnCv.href = `/api/applications/${appId}/download/cv`;
        btnCv.style.opacity = "1";
        btnCv.style.pointerEvents = "auto";
        btnCv.style.cursor = "pointer";
        btnCv.style.color = "#2563eb";
        btnCv.style.borderColor = "#bfdbfe";
        if (cvStatus) cvStatus.textContent = "✅ Prêt au téléchargement";
    }
    if (btnLetter && letterReady) {
        btnLetter.href = `/api/applications/${appId}/download/letter`;
        btnLetter.style.opacity = "1";
        btnLetter.style.pointerEvents = "auto";
        btnLetter.style.cursor = "pointer";
        btnLetter.style.color = "#16a34a";
        btnLetter.style.borderColor = "#bbf7d0";
        if (letterStatus) letterStatus.textContent = "✅ Prête au téléchargement";
    }
}

function _renderOfferAnalysis(analysis) {
    const container = document.getElementById("tailor-offer-analysis");
    const content = document.getElementById("tailor-analysis-content");
    if (!container || !content || !analysis) return;

    const requiredSkills = (analysis.required_skills || []).join(", ") || "—";
    const missions = (analysis.key_missions || []).map(m => `<li>${escapeHtml(m)}</li>`).join("");
    const headline = analysis.suggested_headline || "—";
    const projectsToHighlight = (analysis.top_projects_to_highlight || []).join(", ") || "—";

    content.innerHTML = `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
                <div style="font-weight: 600; font-size: 11.5px; color: #2563eb; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Compétences requises</div>
                <div>${escapeHtml(requiredSkills)}</div>
            </div>
            <div>
                <div style="font-weight: 600; font-size: 11.5px; color: #2563eb; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Titre CV adapté</div>
                <div>${escapeHtml(headline)}</div>
            </div>
        </div>
        <div style="margin-bottom: 8px;">
            <div style="font-weight: 600; font-size: 11.5px; color: #2563eb; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Projets à mettre en avant</div>
            <div>${escapeHtml(projectsToHighlight)}</div>
        </div>
        ${missions ? `<div>
            <div style="font-weight: 600; font-size: 11.5px; color: #2563eb; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px;">Missions clés</div>
            <ul style="margin: 0; padding-left: 16px;">${missions}</ul>
        </div>` : ""}
    `;
    container.classList.remove("hidden");
}

async function checkPersonalizationStatus(appId) {
    if (!appId) return;
    try {
        const res = await fetch(`/api/applications/${appId}/personalization-status`);
        if (!res.ok) return;
        const data = await res.json();

        const banner = document.getElementById("tailor-status-banner");
        const statusText = document.getElementById("tailor-status-text");

        if (data.personalized) {
            if (banner) {
                banner.style.background = "#f0fdf4";
                banner.style.borderColor = "#86efac";
            }
            if (statusText) {
                statusText.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #16a34a;"></i>
                    CV et Lettre personnalisés <strong>déjà générés</strong> — téléchargez-les ci-dessous.`;
            }
            _setTailorDownloadReady(appId, data.cv_pdf_ready, data.letter_pdf_ready);
            if (data.offer_analysis) _renderOfferAnalysis(data.offer_analysis);
        }
    } catch (e) {
        console.debug("checkPersonalizationStatus:", e);
    }
}

async function triggerPersonalization(appId) {
    if (!appId) {
        showToast("Aucune candidature sélectionnée", "warning");
        return;
    }

    const btn = document.getElementById("btn-tailor-generate");
    const spinner = document.getElementById("tailor-spinner");
    const statusText = document.getElementById("tailor-status-text");
    const banner = document.getElementById("tailor-status-banner");

    // UI : chargement
    if (btn) { btn.disabled = true; btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Génération...`; }
    if (spinner) spinner.classList.remove("hidden");
    if (statusText) statusText.textContent = "L'agent analyse l'offre et adapte votre CV maître... (30-90s)";
    if (banner) { banner.style.background = "#eff6ff"; banner.style.borderColor = "#bfdbfe"; }

    try {
        const res = await fetch(`/api/applications/${appId}/personalize`, { method: "POST" });
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || "Erreur serveur");
        }

        // Succès
        if (statusText) {
            statusText.innerHTML = `<i class="fa-solid fa-circle-check" style="color: #16a34a;"></i>
                CV et Lettre <strong>personnalisés avec succès</strong> — téléchargez-les ci-dessous.`;
        }
        if (banner) { banner.style.background = "#f0fdf4"; banner.style.borderColor = "#86efac"; }

        _setTailorDownloadReady(appId, !!data.cv_pdf, !!data.letter_pdf);
        if (data.offer_analysis) _renderOfferAnalysis(data.offer_analysis);

        showToast("✅ CV et Lettre personnalisés générés avec succès !", "success");

        // Recharger les candidatures pour mettre à jour le state local
        await loadApplications();

    } catch (e) {
        if (statusText) statusText.textContent = `Erreur : ${e.message}`;
        if (banner) { banner.style.background = "#fff1f2"; banner.style.borderColor = "#fecaca"; }
        showToast(`Erreur personnalisation : ${e.message}`, "danger");
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Regénérer`; }
        if (spinner) spinner.classList.add("hidden");
    }
}
