'use strict';
const $ = id => document.getElementById(id);
let captured = null;
let currentMode = 'vulnerable';
const text = (tag, value, className) => { const element = document.createElement(tag); element.textContent = String(value ?? '—'); if (className) element.className = className; return element; };
const timestamp = event => typeof event.eventTimestamp === 'number' ? event.eventTimestamp : Date.parse(event.timestamp);
const displayTime = value => { const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Timestamp absent' : date.toISOString().replace('T', ' ').replace('.000Z', 'Z'); };
function renderLogs() {
  const container = $('logs'); container.replaceChildren();
  if (!captured) { container.append(text('p', 'No recorded AWS events available.', 'empty')); return; }
  const sent = captured.messages.find(message => message.mode === currentMode);
  if (!sent) { container.append(text('p', 'No submitted message recorded for this handler.', 'empty')); return; }
  const events = captured.events.filter(event => event.source === 'worker' && event.component === 'worker' && event.runId === captured.runId && event.mode === currentMode && event.messageId === sent.messageId).sort((a, b) => timestamp(a) - timestamp(b));
  const chosen = [events.find(event => event.stage === 'received' && event.receiveCount === 1), events.find(event => event.stage === 'fulfillment_succeeded' && event.receiveCount === 1), events.find(event => event.stage === 'fault_injected'), events.find(event => event.stage === 'received' && event.receiveCount >= 2), events.find(event => event.stage === 'completed' && event.receiveCount >= 2)].filter(Boolean);
  if (!chosen.length) container.append(text('p', 'Required worker observations are missing. Inspect the raw export.', 'empty'));
  for (const event of chosen) {
    const row = text('article', '', 'log-row');
    const heading = text('div', '', 'log-heading');
    heading.append(text('span', `${event.stage} · receive ${event.receiveCount}`, `stage${event.stage === 'fault_injected' ? ' fault' : ''}`), text('time', displayTime(timestamp(event)), 'log-time'));
    const identifiers = text('p', '', 'log-ids');
    identifiers.append(text('span', 'msg '), text('strong', event.messageId), document.createElement('br'), text('span', 'req '), text('strong', event.requestId));
    row.append(heading, identifiers); container.append(row);
  }
}
async function fetchJson(path) {
  const response = await fetch(path, {cache: 'no-store'});
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}
async function loadEvidence() {
  try {
    const data = await fetchJson('./evidence.json');
    if (data.schemaVersion !== 1 || data.provenance !== 'aws' || typeof data.runId !== 'string' || !Array.isArray(data.events) || !Array.isArray(data.messages)) throw new Error('The file is not a supported recorded AWS run');
    const analysis = window.ReplayGuardEvidence.analyzeEvidence(data);
    captured = analysis.data;
    const status = analysis.status;
    $('verdict').textContent = `BROWSER: ${status.toUpperCase()}`; $('verdict').className = `verdict ${status}`;
    $('region').textContent = data.region ?? 'Not recorded'; $('run-id').textContent = data.runId;
    $('recorded').textContent = displayTime(data.recordedAt);
    for (const mode of ['vulnerable', 'repaired']) {
      const receipts = Array.isArray(data.receipts?.[mode]) ? data.receipts[mode] : [];
      $('' + mode + '-count').textContent = String(new Set(receipts.filter(receipt => receipt && receipt.runId === data.runId && receipt.mode === mode).map(receipt => receipt.receiptId).filter(Boolean)).size);
    }
    $('notice').textContent = `Original sample file claims: ${(analysis.claimedStatus || 'not supplied').toUpperCase()}. Supported browser checks: ${analysis.supportedChecksPassed}/${analysis.totalChecks}. AWS origin is unauthenticated; this is not the full Python verifier. Inspect browser check details in the main comparison.`;
    renderLogs();
  } catch (error) {
    $('verdict').textContent = 'INCOMPLETE · NO RUN LOADED';
    $('notice').textContent = `Evidence unavailable: ${error.message}. No AWS result is inferred.`;
    renderLogs();
  }
}
async function loadResources() {
  try {
    const rows = await fetchJson('./aws-resources.json');
    if (!Array.isArray(rows) || !rows.every(row => row && typeof row.type === 'string' && typeof row.status === 'string' && typeof row.name === 'string')) throw new Error('Resource snapshot format is unsupported');
    $('resources').replaceChildren(); $('resource-count').textContent = `${rows.length} resources`;
    for (const resource of rows) {
      const row = text('div', '', 'resource-row'); row.setAttribute('role', 'listitem');
      const name = text('div', ''); name.append(text('span', resource.name, 'resource-name'), text('span', resource.type, 'resource-type'));
      row.append(name, text('span', resource.status, 'resource-status')); $('resources').append(row);
    }
  } catch (error) { $('resources').replaceChildren(text('p', `Resource evidence unavailable: ${error.message}`, 'empty')); }
}
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {
  currentMode = button.dataset.mode;
  document.querySelectorAll('[data-mode]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  renderLogs();
}));
loadEvidence(); loadResources();
