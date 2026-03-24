/* ═══════════════════════════════════════════════════════════════
   EvidionAI — app.js
   Open-source multi-agent research frontend.
   Persistent storage via SQLite API (chats, projects, messages).
   No authentication required.
═══════════════════════════════════════════════════════════════ */

/* ── Endpoints ─────────────────────────────────────────────── */
const API_BASE        = '/api';
const QUERY_ENDPOINT  = `${API_BASE}/ai/process`;
const CANCEL_ENDPOINT = `${API_BASE}/ai/cancel`;
const HEALTH_ENDPOINT = `${API_BASE}/health`;
const CHATS_BASE      = `${API_BASE}/chats`;
const PROJECTS_BASE   = `${API_BASE}/projects`;

/* ── State ─────────────────────────────────────────────────── */
let conversations     = [];
let activeId          = null;
let isLoading         = false;
let renameChatId      = null;
let searchDebounce    = null;
let isSearchActive    = false;
let notifPermission   = false;
let soundEnabled      = localStorage.getItem('evidionai_sound') !== 'off';
let activeAbortCtrl   = null;
let activeRequestId   = null;

let projects          = [];
let activeProjectId   = null;
let renameProjectId   = null;
let projectModalMode  = 'create';

/* ── DOM shortcuts ─────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const appShell         = $('appShell');
const sidebar          = $('sidebar');
const chatMessages     = $('chatMessages');
const welcomeScreen    = $('welcomeScreen');
const queryInput       = $('queryInput');
const sendBtn          = $('sendBtn');
const cancelBtn        = $('cancelBtn');
const chatHistoryEl    = $('chatHistory');
const newChatBtn       = $('newChatBtn');
const topbarTitle      = $('topbarTitle');
const historyModal     = $('historyModal');
const historyModalBody = $('historyModalBody');
const historyModalClose= $('historyModalClose');
const statusDot        = $('statusDot');
const statusText       = $('statusText');


/* ═══════════════════════════════════════════════════════════════
   API HELPER
═══════════════════════════════════════════════════════════════ */
async function apiCall(url, method = 'GET', body = null, retry = true) {
  const headers = { 'Content-Type': 'application/json' };
  const opts = { method, headers };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  let data;
  try { data = await res.json(); } catch { data = {}; }
  if (!res.ok) {
    if (retry && res.status >= 500) {
      await new Promise(r => setTimeout(r, 1500));
      return apiCall(url, method, body, false);
    }
    const err = new Error(data?.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}


/* ═══════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════ */
async function init() {
  appShell.style.display = 'flex';

  await loadProjectsFromDB();

  const lastProjectId = localStorage.getItem('evidionai_last_project');
  if (lastProjectId && projects.find(p => p.id === lastProjectId)) {
    activeProjectId = lastProjectId;
    const proj = projects.find(p => p.id === lastProjectId);
    if (proj && $('recentLabel')) $('recentLabel').textContent = proj.title;
    renderProjects();
  }

  await refreshConversations();
  checkHealth();
  requestNotifPermission();
  updateSoundBtn();

  // Restore last open chat
  const lastId = localStorage.getItem('evidionai_last_chat');
  if (lastId) {
    const c = conversations.find(c => c.id === lastId);
    if (c) await loadConversation(c, false);
    else   localStorage.removeItem('evidionai_last_chat');
  }
}

window.addEventListener('beforeunload', e => {
  if (isLoading) {
    e.preventDefault();
    e.returnValue = 'Research is still running. Cancel it first or wait.';
    return e.returnValue;
  }
});


/* ═══════════════════════════════════════════════════════════════
   HEALTH CHECK
═══════════════════════════════════════════════════════════════ */
async function checkHealth() {
  try {
    const res = await fetch(HEALTH_ENDPOINT, { method: 'GET', signal: AbortSignal.timeout(6000) });
    setStatus(res.ok ? 'online' : 'offline', res.ok ? 'System online' : 'API error');
  } catch { setStatus('offline', 'Offline'); }
}
function setStatus(s, t) { statusDot.className = 'status-dot ' + s; statusText.textContent = t; }


/* ═══════════════════════════════════════════════════════════════
   NOTIFICATIONS + SOUND
═══════════════════════════════════════════════════════════════ */
async function requestNotifPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') { notifPermission = true; return; }
  if (Notification.permission !== 'denied') {
    const perm = await Notification.requestPermission();
    notifPermission = (perm === 'granted');
  }
}
function sendNotification(title, body) {
  if (!notifPermission || document.hasFocus()) return;
  try {
    const n = new Notification(title, { body, icon: '/favicon.ico' });
    setTimeout(() => n.close(), 8000);
    n.onclick = () => { window.focus(); n.close(); };
  } catch {}
}
function playSoundNotification() {
  if (!soundEnabled) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const play = (freq, start, dur, gain = 0.18) => {
      const osc = ctx.createOscillator(); const env = ctx.createGain();
      osc.connect(env); env.connect(ctx.destination); osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
      env.gain.setValueAtTime(0, ctx.currentTime + start);
      env.gain.linearRampToValueAtTime(gain, ctx.currentTime + start + 0.02);
      env.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
      osc.start(ctx.currentTime + start); osc.stop(ctx.currentTime + start + dur);
    };
    play(523, 0, 0.25); play(659, 0.15, 0.3); play(784, 0.3, 0.4);
  } catch {}
}
function updateSoundBtn() {
  const btn = $('soundToggleBtn');
  if (!btn) return;
  const on = soundEnabled;
  btn.title = on ? 'Sound notifications on — click to mute' : 'Sound notifications off — click to enable';
  btn.classList.toggle('sound-btn-active', on);
  btn.querySelector('.sound-icon-on').style.display  = on ? 'block' : 'none';
  btn.querySelector('.sound-icon-off').style.display = on ? 'none'  : 'block';
}
window.toggleSound = function() {
  soundEnabled = !soundEnabled;
  localStorage.setItem('evidionai_sound', soundEnabled ? 'on' : 'off');
  updateSoundBtn();
  showToast(soundEnabled ? 'Sound notifications on' : 'Sound notifications off', 'info', 2000);
};


/* ═══════════════════════════════════════════════════════════════
   CHATS — DB operations
═══════════════════════════════════════════════════════════════ */
async function refreshConversations() {
  try {
    const url = activeProjectId
      ? `${CHATS_BASE}?project_id=${encodeURIComponent(activeProjectId)}`
      : CHATS_BASE;
    const chats = await apiCall(url);
    conversations = chats.map(c => ({
      id: c.id, title: c.title,
      query: c.first_query || c.title,
      timestamp: new Date(c.updated_at),
      project_id: c.project_id || null,
    }));
    renderSidebarHistory();
  } catch(e) { console.error('refreshConversations:', e); }
}

async function createChatInDB(chatId, title, projectId = null) {
  try {
    return await apiCall(CHATS_BASE, 'POST', { id: chatId, title, project_id: projectId || null });
  } catch(e) { console.error('createChat:', e); return null; }
}

async function deleteChatFromDB(chatId) {
  try { await apiCall(`${CHATS_BASE}/${chatId}`, 'DELETE'); return true; }
  catch(e) { console.error('deleteChat:', e); return false; }
}

async function renameChatInDB(chatId, title) {
  try { await apiCall(`${CHATS_BASE}/${chatId}`, 'PUT', { title }); return true; }
  catch(e) { console.error('renameChat:', e); return false; }
}

async function loadChatMessages(chatId) {
  try { return await apiCall(`${CHATS_BASE}/${chatId}/messages`); }
  catch { return []; }
}

async function saveMessageToDB(chatId, role, content, fullHistory = null, status = 'done') {
  try {
    return await apiCall(`${CHATS_BASE}/${chatId}/messages`, 'POST',
      { role, content, full_history: fullHistory, status });
  } catch(e) { console.error('saveMsg:', e); return null; }
}

async function patchMessage(chatId, messageId, content, fullHistory, status) {
  try {
    return await apiCall(`${CHATS_BASE}/${chatId}/messages/${messageId}`, 'PATCH',
      { content, full_history: fullHistory, status });
  } catch(e) { console.error('patchMsg:', e); return null; }
}

async function performSearch(q) {
  try {
    const results = await apiCall(`${CHATS_BASE}/search?q=${encodeURIComponent(q)}`);
    renderSidebarHistory(results.map(c => ({
      id: c.id, title: c.title,
      query: c.first_query || c.title,
      timestamp: new Date(c.updated_at),
      project_id: c.project_id || null,
    })));
  } catch {}
}


/* ═══════════════════════════════════════════════════════════════
   PROJECTS — DB operations
═══════════════════════════════════════════════════════════════ */
async function loadProjectsFromDB() {
  try {
    projects = await apiCall(PROJECTS_BASE);
    renderProjects();
  } catch(e) { console.error('loadProjects:', e); }
}

async function createProjectInDB(id, title) {
  return await apiCall(PROJECTS_BASE, 'POST', { id, title });
}

async function renameProjectInDB(id, title) {
  return await apiCall(`${PROJECTS_BASE}/${id}`, 'PUT', { title });
}

async function deleteProjectInDB(id) {
  return await apiCall(`${PROJECTS_BASE}/${id}`, 'DELETE');
}


/* ═══════════════════════════════════════════════════════════════
   SIDEBAR
═══════════════════════════════════════════════════════════════ */
$('sidebarClose').addEventListener('click', () => sidebar.classList.add('collapsed'));
$('sidebarOpen').addEventListener('click',  () => sidebar.classList.remove('collapsed'));

newChatBtn.addEventListener('click', () => {
  if (isLoading) setLoading(false);
  activeId = null;
  topbarTitle.textContent = 'EvidionAI Research';
  showWelcome();
  queryInput.value = ''; queryInput.style.height = '';
  renderSidebarHistory();
  clearSearch();
});

/* ── Search ────────────────────────────────────────────────── */
const searchInput = $('chatSearchInput');
if (searchInput) {
  searchInput.addEventListener('input', e => {
    const q = e.target.value.trim();
    clearTimeout(searchDebounce);
    if (!q) { isSearchActive = false; renderSidebarHistory(); return; }
    isSearchActive = true;
    searchDebounce = setTimeout(() => performSearch(q), 300);
  });
  searchInput.addEventListener('keydown', e => { if (e.key === 'Escape') clearSearch(); });
}
function clearSearch() {
  if (searchInput) searchInput.value = '';
  isSearchActive = false;
  renderSidebarHistory();
}

function renderSidebarHistory(list) {
  let items;
  if (list) {
    items = list;
  } else if (activeProjectId) {
    items = conversations.filter(c => c.project_id === activeProjectId);
  } else {
    items = conversations.filter(c => !c.project_id);
  }
  chatHistoryEl.innerHTML = '';
  if (!items.length) {
    chatHistoryEl.innerHTML = `<div style="color:var(--text-muted);font-size:12px;padding:8px 12px;">${isSearchActive ? 'No results found' : 'No chats yet'}</div>`;
    return;
  }
  items.forEach(conv => {
    const item = document.createElement('div');
    item.className = 'history-item' + (conv.id === activeId ? ' active' : '');
    const displayTitle = conv.title || 'Untitled';
    item.innerHTML = `
      <svg class="history-item-icon" width="13" height="13" viewBox="0 0 13 13" fill="none">
        <path d="M6.5 1.5C3.739 1.5 1.5 3.739 1.5 6.5S3.739 11.5 6.5 11.5 11.5 9.261 11.5 6.5 9.261 1.5 6.5 1.5z" stroke="currentColor" stroke-width="1.2"/>
        <path d="M6.5 4v3l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      </svg>
      <span class="history-item-text">${escapeHtml(truncate(displayTitle, 36))}</span>
      <div class="history-item-actions">
        <button class="history-action-btn" title="Rename" data-action="rename">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M2 8.5L8.5 2 9.5 3 3 9.5H2V8.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
        </button>
        <button class="history-action-btn history-delete-btn" title="Delete" data-action="delete">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M1.5 3h8M4 3V2h3v1M2.5 3l.5 6.5h5.5L9 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>`;
    item.addEventListener('click', e => {
      if (e.target.closest('[data-action="rename"]')) { openRenameModal(conv.id, e); return; }
      if (e.target.closest('[data-action="delete"]')) { deleteChat(conv.id, e); return; }
      loadConversation(conv);
    });
    chatHistoryEl.appendChild(item);
  });
}

async function deleteChat(chatId, event) {
  event?.stopPropagation();
  if (!confirm('Delete this chat?')) return;
  if (chatId === activeId && isLoading) {
    if (activeAbortCtrl) { activeAbortCtrl.abort(); activeAbortCtrl = null; }
    setLoading(false);
  }
  const ok = await deleteChatFromDB(chatId);
  if (ok) {
    conversations = conversations.filter(c => c.id !== chatId);
    if (activeId === chatId) { activeId = null; showWelcome(); topbarTitle.textContent = 'EvidionAI Research'; }
    renderSidebarHistory();
  }
}

function openRenameModal(chatId, event) {
  event?.stopPropagation();
  renameChatId = chatId;
  const conv = conversations.find(c => c.id === chatId);
  $('renameChatInput').value = conv?.title || '';
  $('renameChatModal').style.display = 'flex';
  setTimeout(() => $('renameChatInput').focus(), 50);
}
function closeRenameModal() { $('renameChatModal').style.display = 'none'; renameChatId = null; }
$('renameChatInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') confirmRenameChat();
  if (e.key === 'Escape') closeRenameModal();
});
async function confirmRenameChat() {
  if (!renameChatId) return closeRenameModal();
  const t = $('renameChatInput').value.trim();
  if (!t) return;
  const ok = await renameChatInDB(renameChatId, t);
  if (ok) {
    const conv = conversations.find(c => c.id === renameChatId);
    if (conv) { conv.title = t; if (activeId === renameChatId) topbarTitle.textContent = t; }
    renderSidebarHistory();
  }
  closeRenameModal();
}


/* ═══════════════════════════════════════════════════════════════
   PROJECTS — UI
═══════════════════════════════════════════════════════════════ */
function renderProjects() {
  const el = $('projectsList');
  if (!el) return;
  if (!projects.length) {
    el.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:4px 12px 8px;opacity:0.6;">No projects yet</div>';
    return;
  }
  el.innerHTML = projects.map(p => {
    const isActive = p.id === activeProjectId;
    return `<div class="project-item ${isActive ? 'project-item--active' : ''}" data-project-id="${p.id}">
      <span class="project-icon">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="3" width="11" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/><path d="M1 5h11" stroke="currentColor" stroke-width="1.2"/><path d="M4 1v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9 1v4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
      </span>
      <span class="project-title">${escapeHtml(p.title)}</span>
      <div class="project-actions">
        <button class="btn-icon project-action-btn" data-action="rename-project" data-id="${p.id}" data-title="${escapeHtml(p.title)}" title="Rename">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M8.5 1.5l2 2L4 10H2V8L8.5 1.5z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/></svg>
        </button>
        <button class="btn-icon project-action-btn" data-action="delete-project" data-id="${p.id}" data-title="${escapeHtml(p.title)}" title="Delete">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 3h8M4 3V2h4v1M5 5.5V9M7 5.5V9M3 3l.5 7h5l.5-7" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </div>`;
  }).join('');

  el.querySelectorAll('.project-item').forEach(item => {
    item.addEventListener('click', async (e) => {
      if (e.target.closest('[data-action]')) return;
      const pid = item.dataset.projectId;
      if (activeProjectId === pid) {
        // Toggle off — go back to all recent chats
        activeProjectId = null;
        localStorage.removeItem('evidionai_last_project');
        if ($('recentLabel')) $('recentLabel').textContent = 'Recent';
        await refreshConversations();
        renderProjects();
      } else {
        activeProjectId = pid;
        localStorage.setItem('evidionai_last_project', pid);
        const proj = projects.find(p => p.id === pid);
        if ($('recentLabel')) $('recentLabel').textContent = proj?.title || 'Project';
        await refreshConversations();
        renderProjects();
        showWelcome();
        activeId = null;
      }
    });
    item.querySelector('[data-action="rename-project"]')?.addEventListener('click', e => {
      e.stopPropagation();
      const btn = e.currentTarget;
      openRenameProjectModal(btn.dataset.id, btn.dataset.title);
    });
    item.querySelector('[data-action="delete-project"]')?.addEventListener('click', e => {
      e.stopPropagation();
      const btn = e.currentTarget;
      deleteProject(btn.dataset.id, btn.dataset.title);
    });
  });
}




function openCreateProjectModal() {
  projectModalMode = 'create';
  $('projectModalTitle').textContent = 'New Project';
  $('projectNameInput').value = '';
  $('projectModal').style.display = 'flex';
  setTimeout(() => $('projectNameInput').focus(), 50);
}
function openRenameProjectModal(id, title) {
  projectModalMode = 'rename';
  renameProjectId = id;
  $('projectModalTitle').textContent = 'Rename Project';
  $('projectNameInput').value = title;
  $('projectModal').style.display = 'flex';
  setTimeout(() => $('projectNameInput').focus(), 50);
}
function closeProjectModal() { $('projectModal').style.display = 'none'; renameProjectId = null; }

async function confirmProjectModal() {
  const title = $('projectNameInput').value.trim();
  if (!title) return;
  if (projectModalMode === 'create') {
    const id = Date.now().toString();
    try {
      const proj = await createProjectInDB(id, title);
      projects.unshift({ id: proj.id || id, title: proj.title || title });
      renderProjects();
      closeProjectModal();
      showToast(`Project "${title}" created`);
    } catch(e) { showToast(`Failed to create project: ${e.message}`, 'error'); }
  } else {
    try {
      await renameProjectInDB(renameProjectId, title);
      const p = projects.find(p => p.id === renameProjectId);
      if (p) { p.title = title; renderProjects(); }
      closeProjectModal();
    } catch(e) { showToast(`Failed to rename: ${e.message}`, 'error'); }
  }
}

async function deleteProject(id, title) {
  if (!confirm(`Delete project "${title}" and all its chats? This cannot be undone.`)) return;
  try {
    await deleteProjectInDB(id);
    projects = projects.filter(p => p.id !== id);
    if (activeProjectId === id) {
      activeProjectId = null;
      localStorage.removeItem('evidionai_last_project');
      if ($('recentLabel')) $('recentLabel').textContent = 'Recent';
      activeId = null;
      showWelcome();
    }
    await refreshConversations();
    renderProjects();
    showToast('Project deleted');
  } catch(e) { showToast('Failed to delete project', 'error'); }
}

$('projectNameInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') confirmProjectModal();
  if (e.key === 'Escape') closeProjectModal();
});


/* ═══════════════════════════════════════════════════════════════
   TEXTAREA & BUTTONS
═══════════════════════════════════════════════════════════════ */
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => { queryInput.value = chip.dataset.query; autoResizeTextarea(); queryInput.focus(); });
});
queryInput.addEventListener('input', autoResizeTextarea);
function autoResizeTextarea() { queryInput.style.height = 'auto'; queryInput.style.height = Math.min(queryInput.scrollHeight, 200) + 'px'; }
queryInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } });
sendBtn.addEventListener('click', handleSend);
cancelBtn.addEventListener('click', handleCancel);


/* ═══════════════════════════════════════════════════════════════
   MAIN SEND
   Flow:
   1. Create chat in DB if new
   2. Save user message (status=done)
   3. Save assistant placeholder (status=pending) — crash-safe
   4. Stream AI request (SSE)
   5. PATCH placeholder → done/error
═══════════════════════════════════════════════════════════════ */
async function handleSend() {
  const query = queryInput.value.trim();
  if (!query || isLoading) return;

  setLoading(true);
  queryInput.value = ''; queryInput.style.height = '';
  showChat();

  // Create or reuse chat
  let chatId = activeId;
  const isNew = !chatId;
  if (isNew) {
    chatId = Date.now().toString();
    activeId = chatId;
    const title = truncate(query, 60);
    await createChatInDB(chatId, title, activeProjectId || null);
    conversations.unshift({ id: chatId, title, query, timestamp: new Date(), project_id: activeProjectId || null });
    renderSidebarHistory();
  }

  topbarTitle.textContent = conversations.find(c => c.id === chatId)?.title || truncate(query, 50);
  appendUserMessage(query);

  await saveMessageToDB(chatId, 'user', query);

  // Save pending slot — if browser is closed, message stays recoverable
  const pendingMsg = await saveMessageToDB(chatId, 'assistant', '', null, 'pending');
  const pendingMsgId = pendingMsg?.id ?? null;

  const agentRow  = appendAgentPlaceholder();
  const startedAt = Date.now();
  animateProgress(agentRow, startedAt);

  const chatContext = await buildChatContext(chatId);

  setStatus('online', 'Researching…');
  activeRequestId = genUUID();
  activeAbortCtrl = new AbortController();

  // Project memory namespace: same project = shared memory across chats
  const memoryId = activeProjectId || chatId;

  (async () => {
    let res;
    try {
      res = await fetch(QUERY_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          chat_context: chatContext,
          request_id: activeRequestId,
          session_id: chatId,
          memory_id: memoryId,
        }),
        signal: activeAbortCtrl.signal,
      });
    } catch (fetchErr) {
      if (fetchErr.name === 'AbortError') { activeAbortCtrl = null; return; }
      activeAbortCtrl = null;
      if (pendingMsgId) await patchMessage(chatId, pendingMsgId, '[ERROR] Could not connect to AI service.', null, 'error');
      renderAgentError(agentRow, 'Could not connect to AI service. Is it running?');
      setLoading(false); setStatus('offline', 'Offline');
      return;
    }

    if (!res.ok) {
      activeAbortCtrl = null;
      const text = await res.text().catch(() => '');
      const msg = `HTTP ${res.status}: ${text.slice(0, 120)}`;
      if (pendingMsgId) await patchMessage(chatId, pendingMsgId, `[ERROR] ${msg}`, null, 'error');
      renderAgentError(agentRow, msg);
      setLoading(false); setStatus('offline', 'Request failed');
      return;
    }

    // ── SSE reader ──────────────────────────────────────────────
    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', curEventType = 'message', curData = null;

    async function dispatchSSE(evType, dataStr) {
      if (!dataStr || dataStr === '{}') return false;       // ping
      if (evType !== 'result' && evType !== 'error') return false;
      let response;
      try { response = JSON.parse(dataStr); } catch { return false; }

      activeRequestId = null; activeAbortCtrl = null;

      if (!conversations.some(c => c.id === chatId)) {
        setLoading(false); return true;
      }

      if (evType === 'result' && response.final_answer &&
          !response.final_answer.startsWith('[Research was cancelled')) {
        if (pendingMsgId)
          await patchMessage(chatId, pendingMsgId, response.final_answer, response.full_history || [], 'done');
        const conv = conversations.find(c => c.id === chatId);
        if (conv) conv.timestamp = new Date();
        renderAgentAnswer(agentRow, response);
        setLoading(false); setStatus('online', 'System online');
        sendNotification('✦ EvidionAI — Research complete', 'Your research query has finished.');
        playSoundNotification();
        showToast('Research complete!', 'success', 4000);
        renderSidebarHistory();
      } else {
        const errMsg = response.final_answer || '[ERROR] Request failed.';
        if (pendingMsgId)
          await patchMessage(chatId, pendingMsgId, errMsg, null, 'error').catch(() => {});
        renderAgentError(agentRow, errMsg);
        setLoading(false);
        if (evType === 'error') { setStatus('offline', 'Request failed'); showToast('Research failed.', 'error', 4000); }
      }
      return true;
    }

    try {
      outer: while (true) {
        const { done, value } = await reader.read();
        if (value) buffer += decoder.decode(value, { stream: !done });
        if (done && buffer.length && !buffer.endsWith('\n')) buffer += '\n';

        let nlIdx;
        while ((nlIdx = buffer.indexOf('\n')) !== -1) {
          const line = buffer.slice(0, nlIdx).replace(/\r$/, '');
          buffer = buffer.slice(nlIdx + 1);
          if (line.startsWith('event:')) {
            curEventType = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const chunk = line.slice(5).trim();
            curData = curData === null ? chunk : curData + '\n' + chunk;
          } else if (line === '') {
            if (curData !== null) {
              const handled = await dispatchSSE(curEventType, curData);
              if (handled) break outer;
            }
            curEventType = 'message'; curData = null;
          }
        }
        if (done) break;
      }
    } catch (streamErr) {
      if (streamErr.name === 'AbortError') { activeAbortCtrl = null; return; }
      activeAbortCtrl = null;
      console.warn('[handleSend] stream error:', streamErr.message);
      if (pendingMsgId) await patchMessage(chatId, pendingMsgId, `[ERROR] ${streamErr.message}`, null, 'error');
      renderAgentError(agentRow, 'Stream error — ' + streamErr.message);
      setLoading(false);
    }
  })();
}

async function buildChatContext(chatId) {
  try {
    const messages = await loadChatMessages(chatId);
    const pairs = [];
    let i = 0;
    while (i < messages.length) {
      const m = messages[i];
      if (m.role === 'user') {
        const next = messages[i + 1];
        if (next && next.role === 'assistant' && next.status === 'done' && next.content) {
          pairs.push({ role: 'user', content: m.content });
          pairs.push({ role: 'assistant', content: next.content.slice(0, 1200) + (next.content.length > 1200 ? '…' : '') });
        }
        i += 2;
      } else i++;
    }
    return pairs.slice(-6); // last 3 exchanges
  } catch { return []; }
}


/* ═══════════════════════════════════════════════════════════════
   CANCEL
═══════════════════════════════════════════════════════════════ */
async function handleCancel() {
  if (!isLoading) return;
  if (activeAbortCtrl) { activeAbortCtrl.abort(); activeAbortCtrl = null; }
  const rid = activeRequestId; activeRequestId = null;
  if (rid) {
    fetch(CANCEL_ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: rid }),
    }).catch(() => {});
  }
  setLoading(false);
  showToast('Research cancelled.', 'info', 3000);
}


/* ═══════════════════════════════════════════════════════════════
   LOAD CONVERSATION
═══════════════════════════════════════════════════════════════ */
async function loadConversation(conv, silent = false) {
  activeId = conv.id;
  if (!silent) topbarTitle.textContent = truncate(conv.title || 'Chat', 50);
  showChat();
  chatMessages.innerHTML = '';
  localStorage.setItem('evidionai_last_chat', conv.id);

  const messages = await loadChatMessages(conv.id);
  if (!messages.length) { showWelcome(); return; }

  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.role === 'user') {
      appendUserMessage(msg.content);
      const next = messages[i + 1];
      if (next && next.role === 'assistant') {
        if (next.status === 'pending') {
          renderInterruptedMessage(msg.content);
        } else if (next.status === 'error') {
          renderInterruptedMessageWithContent(next.content, msg.content);
        } else {
          chatMessages.appendChild(buildCompletedAgentRow({
            final_answer: next.content,
            full_history: next.full_history || [],
          }));
        }
        i += 2;
      } else i++;
    } else i++;
  }
  renderSidebarHistory();
  scrollToBottom();
}


/* ═══════════════════════════════════════════════════════════════
   RENDER HELPERS
═══════════════════════════════════════════════════════════════ */
function appendUserMessage(text) {
  const row = document.createElement('div');
  row.className = 'message-row message-user';
  row.innerHTML = `
    <div class="user-bubble">${escapeHtml(text)}</div>
    <div class="user-actions">
      <button class="msg-copy-btn" title="Copy message">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="3" width="7" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 3V2a1 1 0 011-1h5a1 1 0 011 1v7a1 1 0 01-1 1H9" stroke="currentColor" stroke-width="1.2"/></svg>
        Copy
      </button>
    </div>`;
  row.querySelector('.msg-copy-btn').addEventListener('click', () => copyText(text, row.querySelector('.msg-copy-btn')));
  chatMessages.appendChild(row); scrollToBottom();
}

function renderInterruptedMessage(originalQuery) {
  const row = document.createElement('div');
  row.className = 'message-row';
  const safeQuery = escapeHtml(originalQuery || '');
  row.innerHTML = `
    <div class="message-agent">
      <div class="agent-avatar" style="opacity:.5">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 1L1 4.5L8 8L15 4.5L8 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 11.5L8 15L15 11.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 8L8 11.5L15 8" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="agent-body">
        <div class="agent-name">EvidionAI <span class="agent-name-badge badge-error">Interrupted</span></div>
        <div class="agent-content">
          <div class="interrupted-box">
            <div>
              <div style="font-weight:600;margin-bottom:4px;">Research was interrupted</div>
              <div style="color:var(--text-muted);font-size:12px;margin-bottom:12px;">The server was restarted or the connection dropped. Re-send to continue.</div>
              <button class="resend-btn" data-query="${safeQuery}">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M11 1L1 11M11 1H6M11 1V6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                Re-send query
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  row.querySelector('.resend-btn')?.addEventListener('click', e => {
    const q = e.currentTarget.dataset.query;
    if (q) { queryInput.value = q; queryInput.focus(); autoResizeTextarea(); }
  });
  chatMessages.appendChild(row);
}

function renderInterruptedMessageWithContent(content, originalQuery) {
  const isInterrupt = !content ||
    content.startsWith('[Research was interrupted') ||
    content.startsWith('[Research was cancelled') ||
    content.startsWith('[ERROR]');
  if (isInterrupt) { renderInterruptedMessage(originalQuery); return; }
  const row = buildCompletedAgentRow({ final_answer: content || 'Request failed', full_history: [] });
  const badge = row.querySelector('.agent-name-badge');
  if (badge) { badge.className = 'agent-name-badge badge-error'; badge.textContent = 'Error'; }
  chatMessages.appendChild(row);
}

function buildCompletedAgentRow(data) {
  const row = document.createElement('div');
  row.className = 'message-row';
  row.innerHTML = `
    <div class="message-agent">
      <div class="agent-avatar">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 1L1 4.5L8 8L15 4.5L8 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 11.5L8 15L15 11.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 8L8 11.5L15 8" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="agent-body">
        <div class="agent-name">EvidionAI <span class="agent-name-badge badge-done">Done</span></div>
        <div class="agent-content"></div>
      </div>
    </div>`;
  renderAgentAnswer(row, data);
  return row;
}

function appendAgentPlaceholder() {
  const row = document.createElement('div');
  row.className = 'message-row';
  row.innerHTML = `
    <div class="message-agent">
      <div class="agent-avatar agent-avatar-pulse">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 1L1 4.5L8 8L15 4.5L8 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 11.5L8 15L15 11.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
          <path d="M1 8L8 11.5L15 8" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="agent-body">
        <div class="agent-name">EvidionAI <span class="agent-name-badge badge-running">Researching</span></div>
        <div class="agent-content">
          <div class="thinking-container">
            <div class="thinking-orbs">
              <div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div>
            </div>
            <div class="thinking-stages">
              <div class="stage-ticker">
                <span class="stage-text active">Searching literature &amp; sources</span>
                <span class="stage-text">Formulating research strategy</span>
                <span class="stage-text">Designing experiment</span>
                <span class="stage-text">Writing &amp; executing code</span>
                <span class="stage-text">Analyzing results</span>
                <span class="stage-text">Running skeptic review</span>
                <span class="stage-text">Synthesizing final report</span>
              </div>
            </div>
            <div class="thinking-timeline">
              <div class="timeline-bar"><div class="timeline-fill" id="timelineFill"></div></div>
              <div class="timeline-elapsed" id="timelineElapsed">0s</div>
            </div>
            <div class="thinking-particles" id="thinkingParticles"></div>
          </div>
        </div>
      </div>
    </div>`;
  chatMessages.appendChild(row); scrollToBottom();
  return row;
}

function animateProgress(row, startedAt) {
  const stages = row.querySelectorAll('.stage-text');
  const fill    = row.querySelector('.timeline-fill');
  const elapsed = row.querySelector('.timeline-elapsed');
  const parts   = row.querySelector('.thinking-particles');
  if (parts) {
    for (let i = 0; i < 12; i++) {
      const p = document.createElement('div'); p.className = 'particle';
      p.style.cssText = `left:${Math.random()*100}%;animation-delay:${Math.random()*4}s;animation-duration:${3+Math.random()*4}s;width:${2+Math.random()*3}px;height:${2+Math.random()*3}px;opacity:${.2+Math.random()*.4};`;
      parts.appendChild(p);
    }
  }
  const start = startedAt || Date.now();
  const timer = setInterval(() => { if (elapsed) elapsed.textContent = Math.floor((Date.now()-start)/1000)+'s'; }, 1000);
  row._clearTimer = () => clearInterval(timer);
  const durs = [4000, 3500, 5000, 6000, 4500, 3000, 3500];
  let idx = 0;
  function nextStage() {
    stages.forEach(s => s.classList.remove('active','done'));
    for (let i = 0; i < idx; i++) stages[i]?.classList.add('done');
    if (idx < stages.length) {
      stages[idx].classList.add('active');
      if (fill) fill.style.width = Math.min(((idx+.5)/stages.length)*100,95)+'%';
      row._stageTimeout = setTimeout(nextStage, durs[idx]||4000); idx++;
    } else { idx = stages.length-1; row._stageTimeout = setTimeout(nextStage,4000); }
  }
  nextStage();
}

function renderAgentAnswer(row, data) {
  if (row._clearTimer)   row._clearTimer();
  if (row._stageTimeout) clearTimeout(row._stageTimeout);
  const content = row.querySelector('.agent-content');
  const badge   = row.querySelector('.agent-name-badge');
  if (badge) { badge.className = 'agent-name-badge badge-done'; badge.textContent = 'Done'; }
  const answer  = data.final_answer || '*(No answer returned)*';
  const history = data.full_history || [];
  const revId   = 'rev-' + Date.now();
  content.innerHTML = `
    <div class="answer-content">${parseMarkdown(answer)}</div>
    <div class="answer-actions">
      <button class="answer-action-btn" onclick="exportCurrentChat('pdf')" title="Export PDF">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 2h6l3 3v7a1 1 0 01-1 1H2a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.2"/><path d="M8 2v3h3M4.5 7.5v3M3 9h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        PDF
      </button>
      <button class="answer-action-btn" onclick="exportCurrentChat('md')" title="Export Markdown">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M1 10V3h2l2 2.5L7 3h2v7H7V6.5L5 9 3 6.5V10z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M10 6l1.5 1.5L10 9" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Markdown
      </button>
      <button class="answer-action-btn" id="${revId}" title="Agent trace">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><circle cx="6.5" cy="6.5" r="5" stroke="currentColor" stroke-width="1.2"/><path d="M6.5 4V7l1.5 1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        Trace
      </button>
      <button class="answer-action-btn" id="copy-${revId}" title="Copy answer">
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none"><rect x="1" y="3" width="7" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 3V2a1 1 0 011-1h5a1 1 0 011 1v7a1 1 0 01-1 1H9" stroke="currentColor" stroke-width="1.2"/></svg>
        Copy
      </button>
    </div>`;
  content.querySelector(`#${revId}`)?.addEventListener('click', () => openHistoryModal(history));
  content.querySelector(`#copy-${revId}`)?.addEventListener('click', e => {
    copyText(content.querySelector('.answer-content')?.innerText || '', e.currentTarget);
  });
  content.querySelectorAll('.code-copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const code = btn.closest('.code-block').querySelector('pre').textContent;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="3" width="7" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 3V2a1 1 0 011-1h4a1 1 0 011 1v6a1 1 0 01-1 1H8" stroke="currentColor" stroke-width="1.2"/></svg> Copy`; }, 1500);
      });
    });
  });
  content.querySelectorAll('.think-header').forEach(h => h.addEventListener('click', () => h.closest('.think-block').classList.toggle('open')));
  renderKaTeX(content);
  scrollToBottom();
}

function renderAgentError(row, errMsg) {
  if (row._clearTimer)   row._clearTimer();
  if (row._stageTimeout) clearTimeout(row._stageTimeout);
  const content = row.querySelector('.agent-content');
  const badge   = row.querySelector('.agent-name-badge');
  if (badge) { badge.className = 'agent-name-badge badge-error'; badge.textContent = 'Error'; }
  content.innerHTML = `<div style="color:var(--red);font-size:13px;padding:10px 0;"><strong>Request failed:</strong> ${escapeHtml(errMsg)}</div>`;
}


/* ═══════════════════════════════════════════════════════════════
   HISTORY MODAL
═══════════════════════════════════════════════════════════════ */
function openHistoryModal(fullHistory) {
  historyModalBody.innerHTML = '';
  if (!fullHistory?.length) {
    historyModalBody.innerHTML = '<div style="color:var(--text-muted);font-size:13px;">No history available.</div>';
    historyModal.style.display = 'flex'; return;
  }
  fullHistory.forEach(turn => {
    const div = document.createElement('div');
    div.style.marginBottom = '28px';
    if (turn.iterations !== undefined || turn.start_time || turn.search_results) {
      div.innerHTML += `<div class="history-meta">
        ${turn.iterations !== undefined ? `<div class="history-meta-item">Iterations<span class="history-meta-val">${turn.iterations}</span></div>` : ''}
        ${turn.search_results ? `<div class="history-meta-item">Sources<span class="history-meta-val">${turn.search_results.length}</span></div>` : ''}
        ${turn.code_solutions ? `<div class="history-meta-item">Code<span class="history-meta-val">${turn.code_solutions.length}</span></div>` : ''}
        ${turn.start_time ? `<div class="history-meta-item">Started<span class="history-meta-val">${formatTime(turn.start_time)}</span></div>` : ''}
        ${turn.end_time ? `<div class="history-meta-item">Ended<span class="history-meta-val">${formatTime(turn.end_time)}</span></div>` : ''}
      </div>`;
    }
    if (turn.query) div.innerHTML += `<div class="history-query-block"><div class="history-query-label">Query</div><div class="history-query-text">${escapeHtml(turn.query)}</div></div>`;
    if (turn.history?.length) {
      const t = document.createElement('div');
      t.style.cssText = 'font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);font-weight:600;margin-bottom:10px;font-family:var(--font-mono)';
      t.textContent = `Agent Messages (${turn.history.length})`;
      div.appendChild(t);
      turn.history.forEach((msg, mi) => {
        const d = document.createElement('div'); d.className = 'history-turn';
        const c = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2);
        d.innerHTML = `<div class="history-turn-header"><span class="history-turn-role">${escapeHtml(msg.role||'?')}</span><span>${mi+1}/${turn.history.length}</span></div><div class="history-turn-body">${escapeHtml(c)}</div>`;
        div.appendChild(d);
      });
    }
    historyModalBody.appendChild(div);
  });
  historyModal.style.display = 'flex';
}
historyModalClose.addEventListener('click', () => historyModal.style.display = 'none');
historyModal.addEventListener('click', e => { if (e.target === historyModal) historyModal.style.display = 'none'; });
$('renameChatModal').addEventListener('click', e => { if (e.target === $('renameChatModal')) closeRenameModal(); });


/* ═══════════════════════════════════════════════════════════════
   EXPORT
═══════════════════════════════════════════════════════════════ */
function exportCurrentChat(format) {
  if (!activeId) return showToast('Open a chat first', 'warning');
  const conv = conversations.find(c => c.id === activeId);
  const title = conv?.title || 'Research';
  const messages = [];
  chatMessages.querySelectorAll('.message-row').forEach(row => {
    const ub = row.querySelector('.user-bubble');
    if (ub) messages.push({ role: 'user', text: ub.textContent });
    const ac = row.querySelector('.answer-content');
    if (ac) messages.push({ role: 'assistant', html: ac.innerHTML, text: ac.innerText });
  });
  if (!messages.length) return showToast('No content to export', 'warning');
  if (format === 'md') exportMarkdown(title, messages);
  else exportPDF(title, messages);
}
function exportMarkdown(title, messages) {
  let md = `# ${title}\n\n*Exported from EvidionAI Research Platform*\n\n---\n\n`;
  messages.forEach(m => {
    if (m.role === 'user') md += `## 🔬 Research Query\n\n${m.text}\n\n`;
    else md += `## ✦ EvidionAI Response\n\n${m.text}\n\n---\n\n`;
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = `${sanitizeFilename(title)}.md`; a.click();
  URL.revokeObjectURL(url); showToast('Markdown exported', 'success');
}
function exportPDF(title, messages) {
  let body = '';
  messages.forEach(m => {
    if (m.role === 'user') body += `<div class="user-msg"><div class="label">Research Query</div><p>${escapeHtml(m.text)}</p></div>`;
    else body += `<div class="agent-msg"><div class="label">EvidionAI Response</div><div class="content">${m.html||escapeHtml(m.text)}</div></div>`;
  });
  const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"/><title>${escapeHtml(title)}</title>
    <style>*{box-sizing:border-box;margin:0;padding:0;}body{font-family:'Georgia',serif;font-size:13pt;color:#1a1a2e;background:#fff;padding:40px;max-width:820px;margin:0 auto;line-height:1.7;}
    h1{font-size:22pt;margin-bottom:6px;}.meta{font-size:10pt;color:#666;margin-bottom:32px;padding-bottom:16px;border-bottom:1px solid #ddd;}
    .user-msg,.agent-msg{margin-bottom:28px;padding:20px 24px;border-radius:8px;}.user-msg{background:#f0f0ff;border-left:4px solid #6c5ce7;}.agent-msg{background:#f9f9f9;border-left:4px solid #10b981;}
    .label{font-size:9pt;font-weight:700;text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px;color:#666;}.user-msg .label{color:#6c5ce7;}.agent-msg .label{color:#10b981;}
    h2,h3{margin:18px 0 8px;}p{margin-bottom:10px;}pre{background:#f0f0f0;padding:12px;border-radius:4px;overflow-x:auto;font-size:10pt;}
    @media print{body{padding:20px;}.user-msg,.agent-msg{break-inside:avoid;}}</style>
  </head><body><h1>${escapeHtml(title)}</h1>
  <div class="meta">EvidionAI · ${new Date().toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric'})}</div>${body}</body></html>`;
  const w = window.open('','_blank','width=900,height=700');
  w.document.write(html); w.document.close();
  setTimeout(() => { w.focus(); w.print(); }, 400);
  showToast('PDF print dialog opened', 'success');
}
function sanitizeFilename(s) { return (s||'research').replace(/[^a-z0-9_\-\s]/gi,'_').replace(/\s+/g,'-').slice(0,60); }


/* ═══════════════════════════════════════════════════════════════
   KEYBOARD SHORTCUTS
═══════════════════════════════════════════════════════════════ */
document.addEventListener('keydown', e => {
  if ((e.ctrlKey||e.metaKey) && e.key==='k') { e.preventDefault(); const s=$('chatSearchInput'); if(s){s.focus();s.select();} }
  if (e.key==='Escape') {
    ['historyModal','renameChatModal','projectModal'].forEach(id=>{const m=$(id);if(m&&m.style.display!=='none')m.style.display='none';});
  }
  if ((e.ctrlKey||e.metaKey) && e.key==='Enter' && document.activeElement===queryInput) { e.preventDefault(); handleSend(); }
});


/* ═══════════════════════════════════════════════════════════════
   TOAST
═══════════════════════════════════════════════════════════════ */
function showToast(msg, type='info', duration=3500) {
  let container = $('toastContainer');
  if (!container) {
    container = document.createElement('div'); container.id = 'toastContainer';
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
    document.body.appendChild(container);
  }
  const t = document.createElement('div');
  const colors = {info:'#7c6af5',success:'#10b981',error:'#ef4444',warning:'#f59e0b'};
  t.style.cssText = `background:var(--bg-secondary);border:1px solid ${colors[type]||colors.info};color:var(--text-primary);padding:12px 16px;border-radius:10px;font-size:13px;font-family:var(--font-sans);max-width:320px;box-shadow:0 4px 20px rgba(0,0,0,.4);pointer-events:auto;cursor:pointer;transition:opacity .3s;line-height:1.5;border-left:3px solid ${colors[type]||colors.info};`;
  t.textContent = msg; t.onclick = () => t.remove();
  container.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, duration);
}


/* ═══════════════════════════════════════════════════════════════
   DOM UTILITIES
═══════════════════════════════════════════════════════════════ */
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 13 13" fill="none"><path d="M2 7l3 3 6-6" stroke="#10b981" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg> Copied!`;
    btn.style.color = '#10b981';
    setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 2000);
  }).catch(() => showToast('Copy failed', 'error'));
}
function showWelcome() { welcomeScreen.style.display='flex'; chatMessages.style.display='none'; chatMessages.innerHTML=''; localStorage.removeItem('evidionai_last_chat'); }
function showChat()    { welcomeScreen.style.display='none'; chatMessages.style.display='block'; if(activeId) localStorage.setItem('evidionai_last_chat',activeId); }
function scrollToBottom() { setTimeout(() => { chatMessages.scrollTop=chatMessages.scrollHeight; const b=$('scrollBottomBtn'); if(b) b.style.display='none'; }, 50); }
chatMessages.addEventListener('scroll', () => {
  const btn = $('scrollBottomBtn'); if (!btn) return;
  btn.style.display = (chatMessages.scrollHeight-chatMessages.scrollTop-chatMessages.clientHeight>120)?'flex':'none';
});
function setLoading(s) { isLoading=s; sendBtn.disabled=s; queryInput.disabled=s; sendBtn.style.display=s?'none':''; cancelBtn.style.display=s?'flex':'none'; }
function escapeHtml(s) { if(typeof s!=='string')s=String(s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function truncate(s,n) { return s&&s.length>n?s.slice(0,n)+'…':s; }
function genUUID() { return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16)); }
function formatTime(iso) { try{return new Date(iso).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});}catch{return iso;} }
function togglePw(inputId) { const inp=$(inputId); if(inp) inp.type=inp.type==='password'?'text':'password'; }
function escHtml(s) { return escapeHtml(s); }


/* ═══════════════════════════════════════════════════════════════
   KaTeX
═══════════════════════════════════════════════════════════════ */
const _katexQueue = []; let _katexReady = false;
function _runKatex(el) {
  if(!el) return;
  el.querySelectorAll('.latex-block[data-tex],.latex-inline[data-tex]').forEach(node => {
    if(node.querySelector('.katex')) return;
    let tex=''; try{tex=decodeURIComponent(escape(atob(node.dataset.tex||'')));}catch{tex=node.dataset.tex||'';}
    if(!tex) return;
    const display=node.classList.contains('latex-block');
    try{node.innerHTML=window.katex.renderToString(tex,{displayMode:display,throwOnError:false,output:'html'});}
    catch{node.textContent=tex;}
  });
}
function renderKaTeX(el) {
  if(!el) return;
  if(window.katex){_runKatex(el);}
  else{el.querySelectorAll('.latex-block[data-tex],.latex-inline[data-tex]').forEach(n=>{try{n.textContent=decodeURIComponent(escape(atob(n.dataset.tex||'')));n.style.fontFamily='monospace';}catch{}});}
}
window._onKaTeXReady=function(){_katexReady=true;_katexQueue.splice(0).forEach(el=>_runKatex(el));};
window.addEventListener('load',()=>{if(window.katex&&!_katexReady)window._onKaTeXReady();});


/* ═══════════════════════════════════════════════════════════════
   MARKDOWN PARSER
═══════════════════════════════════════════════════════════════ */
function parseMarkdown(md) {
  if(!md) return '';
  const _s=[];
  const stash=str=>{const i=_s.length;_s.push(str);return `\x00S${i}\x00`;};
  const unstash=s=>s.replace(/\x00S(\d+)\x00/g,(_,i)=>_s[+i]);
  md=md.replace(/<think>([\s\S]*?)<\/think>/gi,(_,c)=>stash(`<div class="think-block"><div class="think-header"><svg class="think-chevron" width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M4 2L8 6L4 10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>Internal reasoning</div><div class="think-body">${escapeHtml(c.trim())}</div></div>`));
  md=md.replace(/```latex\n?([\s\S]*?)```/gi,(_,c)=>stash(`<div class="latex-block" data-tex="${btoa(unescape(encodeURIComponent(c.trim())))}"></div>`));
  md=md.replace(/\$\$([\s\S]+?)\$\$/g,(_,t)=>stash(`<div class="latex-block" data-tex="${btoa(unescape(encodeURIComponent(t.trim())))}"></div>`));
  md=md.replace(/\$([^\$\n]{1,200}?)\$/g,(_,t)=>stash(`<span class="latex-inline" data-tex="${btoa(unescape(encodeURIComponent(t.trim())))}"></span>`));
  md=md.replace(/```(\w*)\n?([\s\S]*?)```/g,(_,l,c)=>stash(`<div class="code-block"><div class="code-block-header"><span class="code-block-lang">${escapeHtml(l||'text')}</span><button class="code-copy-btn"><svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="3" width="7" height="8" rx="1" stroke="currentColor" stroke-width="1.2"/><path d="M4 3V2a1 1 0 011-1h4a1 1 0 011 1v6a1 1 0 01-1 1H8" stroke="currentColor" stroke-width="1.2"/></svg> Copy</button></div><pre><code>${escapeHtml(c.trim())}</code></pre></div>`));
  md=md.replace(/`([^`]+)`/g,(_,c)=>stash(`<code>${escapeHtml(c)}</code>`));
  md=md.replace(/^#{1}\s(.+)$/gm,'<h1>$1</h1>');
  md=md.replace(/^#{2}\s(.+)$/gm,'<h2>$1</h2>');
  md=md.replace(/^#{3}\s(.+)$/gm,'<h3>$1</h3>');
  md=md.replace(/^---$/gm,'<hr>');
  md=md.replace(/^>\s(.+)$/gm,'<blockquote>$1</blockquote>');
  md=parseTable(md);
  md=md.replace(/((?:^[-*+]\s.+\n?)+)/gm,m=>`<ul>${m.trim().split('\n').map(l=>`<li>${l.replace(/^[-*+]\s/,'')}</li>`).join('')}</ul>`);
  md=md.replace(/((?:^\d+\.\s.+\n?)+)/gm,m=>`<ol>${m.trim().split('\n').map(l=>`<li>${l.replace(/^\d+\.\s/,'')}</li>`).join('')}</ol>`);
  md=md.replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>');
  md=md.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  md=md.replace(/\*(.+?)\*/g,'<em>$1</em>');
  const _b2=[];
  md=md.replace(/(<(?:div|ul|ol|table|blockquote|h[1-6]|pre)[^>]*?>[\s\S]*?<\/(?:div|ul|ol|table|blockquote|h[1-6]|pre)>|<hr\s*\/?>)/gi,m=>{const i=_b2.length;_b2.push(m);return `\x00BLK${i}\x00`;});
  md=md.split('\n').map(line=>{const t=line.trim();if(!t)return '';if(t.startsWith('\x00BLK')||t.startsWith('\x00S'))return t;return `<p>${t}</p>`;}).join('\n');
  _b2.forEach((b,i)=>{md=md.split(`\x00BLK${i}\x00`).join(b);});
  return unstash(md);
}
function parseTable(md) {
  return md.replace(/^\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)+)/gm,(_,h,rows)=>{
    const th=h.split('|').map(x=>x.trim()).filter(Boolean).map(x=>`<th>${x}</th>`).join('');
    const tr=rows.trim().split('\n').map(r=>`<tr>${r.split('|').map(c=>c.trim()).filter(Boolean).map(c=>`<td>${c}</td>`).join('')}</tr>`).join('');
    return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  });
}


/* ── RUN ─────────────────────────────────────────────────────── */
init();
