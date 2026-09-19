(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const labels = { pass: 'Passed', violation: 'Violation', incomplete: 'Incomplete', unresolved: 'Unresolved' };
  const cache = new Map();
  let active = null, caseId = null, candidateId = null, source = 'reference', toastTimer, loadToken = 0;
  const defaults = { reference: './repair-example.json', transfer: './repair-transfer.json' };
  function element(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const status = value => element('span', { class: 'status ' + value, text: labels[value] });
  const short = value => String(value).length > 18 ? String(value).slice(0, 16) + '…' : String(value);
  const pretty = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  function candidateDescription(candidate) {
    const id = candidate.id.toLowerCase();
    if (/overbroad|run-only|broad/.test(id)) return 'One key shared by different orders.';
    if (/no-key|unprotected|vulnerable/.test(id)) return 'Every attempt creates a new receipt.';
    if (/business|correct|stable/.test(id)) return 'One stable key per business order.';
    return 'An independently supplied Python adapter.';
  }
  const displayCandidates = model => [...model.candidates.values()].sort((a,b) => { const order = ['no-key','overbroad-key','business-key']; const rank = id => order.includes(id) ? order.indexOf(id) : 3; return rank(a.id)-rank(b.id); });
  function makeComparison(model, selectedCase, selectedCandidate) {
    const plan = model.plans.get(selectedCase), candidates = displayCandidates(model);
    const header = element('tr', {}, element('th', { scope: 'col', text: 'Expected business order' }));
    const body = document.createDocumentFragment();
    const foot = element('tr', {}, element('td', { text: 'Receipt = simulated fulfillment' }));
    for (const candidate of candidates) {
      const result = model.get(selectedCase, candidate.id);
      const button = element('button', { class: 'candidate-button', type: 'button', 'aria-pressed': String(candidate.id === selectedCandidate), 'data-candidate': candidate.id }, element('span', { class: 'candidate-title', text: candidate.title }), element('span', { class: 'candidate-subtitle', text: candidateDescription(candidate) }));
      header.append(element('th', { scope: 'col' }, button, status(result.status)));
      foot.append(element('td', {}, element('button', { class: 'inspect-link', type: 'button', 'data-inspect': candidate.id, text: 'Inspect this candidate' })));
    }
    for (const expected of plan.expectedOrders) {
      const order = expected.order;
      const row = element('tr', {}, element('th', { scope: 'row' }, element('span', { class: 'order-symbol', 'aria-hidden': 'true', text: '◇' }), element('span', { class: 'order-name', text: order.orderId }), element('span', { class: 'order-meta', text: order.sku + '\nQuantity ' + order.quantity + ' · Expected 1 receipt' })));
      for (const candidate of candidates) {
        const view = model.get(selectedCase, candidate.id), count = view.counts[order.orderId];
        const payloadWrong = view.result.receipts?.some(r => r.order.orderId === order.orderId && RepairContract.canonical(r.order) !== RepairContract.canonical(order));
        const state = count === null ? 'incomplete' : count === 1 && !payloadWrong ? 'pass' : 'violation';
        const cell = element('td', { 'data-state': state, 'data-order': order.orderId, 'data-candidate': candidate.id }, element('div', { class: 'count-line' }, element('strong', { class: 'receipt-count', text: count === null ? '—' : count }), element('span', { class: 'count-label', text: count === null ? 'unknown' : count === 1 ? 'receipt' : 'receipts' })));
        if (count === null) cell.append(element('div', { class: 'missing-ticket unknown', text: 'No observer snapshot. Outcome unknown.' }));
        else if (count === 0) cell.append(element('div', { class: 'missing-ticket', text: 'No receipt for this valid order.' }));
        else {
          const receipts = view.result.receipts.filter(r => r.order.orderId === order.orderId);
          receipts.slice(0, 3).forEach((receipt, index) => cell.append(element('div', { class: 'ticket-mini' + (index ? ' duplicate' : '') }, element('code', { title: receipt.receiptId, text: short(receipt.receiptId) }), element('span', { text: RepairContract.canonical(receipt.order) !== RepairContract.canonical(order) ? 'Wrong input' : index ? 'Duplicate' : 'Accepted' }))));
          if (receipts.length > 3) cell.append(element('p', { class: 'small-note', text: '+ ' + (receipts.length - 3) + ' additional receipts in JSON' }));
        }
        row.append(cell);
      }
      body.append(row);
    }
    return { header, body, foot };
  }
  function finding(view) {
    const entries = Object.entries(view.counts), duplicates = entries.filter(([, n]) => n > 1), missing = entries.filter(([, n]) => n === 0);
    if (view.status === 'pass') return { title: view.plan.deliveries.some(d => d.expect === 'conflict') ? 'Changed inputs rejected. Original orders preserved.' : 'Every expected order has exactly one receipt.', detail: 'The observed receipts and required delivery outcomes satisfy this finite local case. This is not a guarantee for untested inputs or an external fulfillment service.' };
    if (view.status === 'unresolved') return { title: view.plan.effectModel !== 'receiver-owned-receipt' ? 'This effect is outside the supported contract.' : 'These observations cannot establish a consistent result.', detail: view.plan.effectModel !== 'receiver-owned-receipt' ? 'No external shipment, payment or email was executed. An atomic receipt is the only supported effect model.' : 'A blocked operation or contradictory evidence prevents a resolved verdict. Open the checks below for the exact reason.' };
    if (view.status === 'incomplete') return { title: view.result.receipts === null ? 'The receipt observation is missing.' : 'Required execution evidence is incomplete.', detail: view.result.receipts === null ? 'A worker response cannot replace an independent snapshot. The receipt counts stay unknown until that observation exists.' : 'Some required delivery or fault evidence is absent. Inspect the execution checks before treating this candidate as repaired.' };
    if (missing.length) return { title: missing.length === 1 ? missing[0][0] + ' was not fulfilled.' : 'Legitimate orders are missing receipts.', detail: 'The repair rejected or skipped ' + missing.map(([id]) => id).join(', ') + ' during the declared schedule.' + (duplicates.length ? ' Other orders also produced duplicate receipts.' : ' Stopping a duplicate does not justify blocking a different valid order.') };
    if (duplicates.length) return { title: 'A repeated delivery created extra fulfillment.', detail: duplicates.map(([id, n]) => id + ' has ' + n + ' receipts instead of 1.').join(' ') + ' The observer counted the committed effects independently of the handler response.' };
    return { title: 'The observed behavior violates the case contract.', detail: 'The receipt payload or required completion behavior differs from the declared expectation. Inspect the failing check below.' };
  }
  function checkTitle(check) {
    const names = { 'source-loaded': 'Candidate loaded successfully', 'source-unchanged': 'Candidate source stayed unchanged', 'bounded-local-execution': 'Execution stayed within the local boundary', 'schedule-executed': 'Every declared delivery was attempted', 'independent-snapshot': 'Observer supplied a receipt snapshot', 'receipt-inputs': 'Receipts match the declared orders', 'receipt-delivery-links': 'Receipts and delivery records agree' };
    if (check.id.startsWith('order:')) return 'Exactly one receipt for ' + check.id.slice(6);
    if (check.id.startsWith('delivery:')) return check.id.slice(9) + ' has the required outcome';
    if (check.id.startsWith('execution:')) return 'Execution error: ' + check.id.slice(10);
    return names[check.id] || check.id.replace(/-/g, ' ');
  }
  function makeInspector(model, selectedCase, selectedCandidate) {
    const view = model.get(selectedCase, selectedCandidate), candidate = model.candidates.get(selectedCandidate);
    const checks = document.createDocumentFragment(), trace = document.createDocumentFragment(), sources = element('dl');
    for (const check of view.checks) {
      const summary = element('summary', {}, element('span', { class: 'assertion-sign ' + check.status, 'aria-label': labels[check.status], text: check.status === 'pass' ? '✓' : check.status === 'violation' ? '×' : '?' }), element('span', { text: checkTitle(check) }));
      const detail = element('div', { class: 'assertion-content' }, element('p', { text: check.detail }), element('dl', {}, element('dt', { text: 'Expected' }), element('dd', { text: pretty(check.expected) }), element('dt', { text: 'Observed' }), element('dd', { text: pretty(check.observed) })));
      checks.append(element('details', { class: 'assertion' }, summary, detail));
    }
    const eventNames = { 'delivery-start': 'Delivery started', 'delivery-end': 'Delivery finished', 'receipt-accepted': 'Receipt committed', 'receipt-reused': 'Existing receipt reused', 'payload-conflict': 'Changed payload rejected', 'fault-injected': 'Response interrupted after commit', 'delivery-completed': 'Handler completed', 'delivery-crashed': 'Configured crash observed', 'delivery-conflict': 'Handler surfaced a conflict', 'delivery-error': 'Handler raised an error' };
    for (const event of view.result.events) {
      const detail = [event.deliveryId, event.orderId || event.order?.orderId, event.receiptId ? 'Receipt ' + short(event.receiptId) : null].filter(Boolean).join(' · ');
      trace.append(element('li', { class: /fault|crash|conflict|error/.test(event.type) ? 'fault' : '' }, element('strong', { text: eventNames[event.type] || event.type.replace(/[-_]/g, ' ') }), element('p', { text: detail || 'Runner observation ' + (event.index + 1) })));
    }
    if (!view.result.events.length) trace.append(element('li', {}, element('strong', { text: 'No execution trace' }), element('p', { text: 'This case did not produce execution events. No outcome is invented.' })));
    const sourcePairs = [['Adapter', candidate.adapter], ...Object.entries(candidate.sourceSha256), ['Candidate loaded / built', String(view.result.execution.imported) + ' / ' + String(view.result.execution.built)], ['Observed deliveries', String(view.result.deliveries.length)], ['Execution origin', 'Local process with simulated receiver; imported origin unauthenticated']];
    sourcePairs.forEach(([key, value]) => sources.append(element('dt', { text: key }), element('dd', { text: value })));
    return { view, finding: finding(view), checks, trace, sources };
  }
  function prepare(model, selectedCase, selectedCandidate) {
    const comparison = makeComparison(model, selectedCase, selectedCandidate), inspector = makeInspector(model, selectedCase, selectedCandidate), plan = model.plans.get(selectedCase);
    const steps = document.createDocumentFragment();
    for (const [i, d] of plan.deliveries.entries()) steps.append(element('li', {}, element('span', { class: 'delivery-chip' + (d.fault !== 'none' ? ' fault' : '') }, document.createTextNode(d.order.orderId), element('small', { text: 'Delivery ' + (i + 1) + (d.fault !== 'none' ? ' · crash after commit' : d.expect === 'conflict' ? ' · expect conflict' : d.receiveCount > 1 ? ' · retry' : '') }))));
    const cases = [...model.plans.values()].map(c => element('option', { value: c.id, text: c.title }));
    const candidates = displayCandidates(model).map(c => element('option', { value: c.id, text: c.title }));
    return { comparison, inspector, steps, cases, candidates, plan };
  }
  function commit(entry, selectedCase, selectedCandidate, selectedSource, prepared) {
    const { comparison, inspector, plan } = prepared;
    $('comparison-head').replaceChildren(comparison.header); $('comparison-body').replaceChildren(comparison.body); $('comparison-foot').replaceChildren(comparison.foot);
    $('case-select').replaceChildren(...prepared.cases); $('case-select').value = selectedCase; $('candidate-select').replaceChildren(...prepared.candidates); $('candidate-select').value = selectedCandidate;
    $('case-title').textContent = plan.title; $('case-description').textContent = plan.description;
    $('schedule-steps').replaceChildren(prepared.steps); $('schedule-bound').textContent = plan.deliveries.length + ' deliveries · finite schedule';
    $('finding').dataset.state = inspector.view.status; $('finding-status').className = 'status ' + inspector.view.status; $('finding-status').textContent = labels[inspector.view.status];
    $('finding-title').textContent = inspector.finding.title; $('finding-description').textContent = inspector.finding.detail;
    $('assertion-list').replaceChildren(inspector.checks); $('execution-trace').replaceChildren(inspector.trace); $('source-details').replaceChildren(inspector.sources);
    const reportedAt = entry.model.report.recordedAt || entry.model.report.generatedAt || entry.model.report.startedAt;
    const date = reportedAt && !Number.isNaN(Date.parse(reportedAt)) ? new Date(reportedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Time not supplied';
    $('report-origin').textContent = selectedSource === 'import' ? 'Imported local run · origin unauthenticated' : selectedSource === 'transfer' ? 'Recorded independent-worker execution' : 'Recorded local comparison';
    $('report-meta').textContent = date + ' · ' + entry.model.plans.size + ' cases · ' + entry.model.candidates.size + ' candidates. The browser inspects; Python executes.';
    $('report-select').value = selectedSource; $('loading-error').hidden = true; $('bench-content').hidden = false; $('json-button').disabled = false;
    active = entry; caseId = selectedCase; candidateId = selectedCandidate; source = selectedSource;
  }
  function accept(entry, selectedSource, keepSelection = false) {
    const cases = [...entry.model.plans.keys()], candidates = [...entry.model.candidates.keys()];
    const selectedCase = keepSelection && entry.model.plans.has(caseId) ? caseId : cases.find(id => id.includes('interleaved')) || cases[0];
    const selectedCandidate = keepSelection && entry.model.candidates.has(candidateId) ? candidateId : candidates.find(id => /overbroad|run-only/.test(id)) || candidates[0];
    const prepared = prepare(entry.model, selectedCase, selectedCandidate);
    commit(entry, selectedCase, selectedCandidate, selectedSource, prepared);
  }
  function decode(bytes, name) {
    if (bytes.byteLength > 8 * 1024 * 1024) throw new Error('Choose a report smaller than 8 MiB.');
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const report = JSON.parse(text), model = RepairContract.validate(report);
    return { model, text, bytes, name };
  }
  function message(text, error = false) { $('import-status').textContent = text; $('import-status').classList.toggle('error', error); }
  async function load(which) {
    const token = ++loadToken;
    try {
      if (which === 'import') { if (!cache.has('import')) throw new Error('Import a generated run first.'); accept(cache.get('import'), which, true); return; }
      let entry = cache.get(which);
      if (!entry) { const response = await fetch(defaults[which]); if (!response.ok) throw new Error('Report unavailable (HTTP ' + response.status + ').'); entry = decode(new Uint8Array(await response.arrayBuffer()), which === 'transfer' ? 'repair-transfer.json' : 'repair-example.json'); }
      if (token !== loadToken) return;
      accept(entry, which); cache.set(which, entry); message('');
    } catch (error) {
      if (token !== loadToken) return;
      $('report-select').value = source;
      if (active) message(error.message + ' Your previous comparison is unchanged.', true);
      else { $('loading-error').hidden = false; $('load-error-detail').textContent = error.message; $('report-origin').textContent = 'Report unavailable'; $('report-meta').textContent = 'Run the kit or import a generated repair report.'; }
    }
  }
  async function importFile(file) {
    if (!file) return;
    ++loadToken;
    try {
      if (file.size > 8 * 1024 * 1024) throw new Error('Choose a report smaller than 8 MiB.');
      const entry = decode(new Uint8Array(await file.arrayBuffer()), file.name);
      accept(entry, 'import'); cache.set('import', entry); $('report-select').querySelector('option[value=import]').disabled = false; $('report-select').value = 'import';
      message('Imported ' + file.name + '. Counts and outcomes were checked against the supplied observations; origin remains unauthenticated.');
    } catch (error) { message('Could not import: ' + error.message + (active ? ' Your previous comparison is unchanged.' : ''), true); }
    $('report-file').value = '';
  }
  function selectCandidate(id, scroll = false) {
    if (!active?.model.candidates.has(id)) return;
    const prepared = prepare(active.model, caseId, id); commit(active, caseId, id, source, prepared);
    if (scroll) { $('inspector').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }); $('candidate-select').focus({ preventScroll: true }); }
  }
  function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; }, 2400); }
  function download() {
    if (!active) return; const url = URL.createObjectURL(new Blob([active.bytes], { type: 'application/json' })); const anchor = element('a', { href: url, download: active.name }); document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('report-select').addEventListener('change', e => load(e.target.value));
  $('case-select').addEventListener('change', e => { const id = e.target.value; if (active?.model.plans.has(id)) commit(active, id, candidateId, source, prepare(active.model, id, candidateId)); });
  $('candidate-select').addEventListener('change', e => selectCandidate(e.target.value));
  $('comparison-table').addEventListener('click', e => { const button = e.target.closest('button'); if (!button) return; if (button.dataset.candidate) selectCandidate(button.dataset.candidate); else if (button.dataset.inspect) selectCandidate(button.dataset.inspect, true); });
  ['import-button', 'import-bottom'].forEach(id => $(id).addEventListener('click', () => $('report-file').click()));
  $('report-file').addEventListener('change', e => importFile(e.target.files[0]));
  $('retry-load').addEventListener('click', () => load(source));
  $('json-button').addEventListener('click', () => { if (!active) return; $('raw-json').textContent = active.text; $('json-dialog').showModal(); });
  $('close-json').addEventListener('click', () => $('json-dialog').close());
  $('json-dialog').addEventListener('click', e => { if (e.target === $('json-dialog')) { const r = e.target.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close(); } });
  $('download-json').addEventListener('click', download);
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => { const text = $(button.dataset.copy).textContent.trim(); try { await navigator.clipboard.writeText(text); toast('Command copied'); } catch { const range = document.createRange(); range.selectNodeContents($(button.dataset.copy)); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); toast('Command selected. Copy with your keyboard.'); } }));
  load('reference');
})();
