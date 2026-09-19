(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const D = window.ProposalData;
  const labels = { pass: 'Passed', violation: 'Violation', incomplete: 'Incomplete', unresolved: 'Unresolved' };
  const signs = { pass: '✓', violation: '×', incomplete: '◌', unresolved: '?' };
  const policies = {
    'no-key': { title: 'No key', key: 'None' },
    'overbroad-key': { title: 'Product key', key: 'sku' },
    'business-key': { title: 'Order key', key: 'orderId' }
  };
  const caseNames = {
    'clean-orders': 'Two ordinary orders', 'crash-retry': 'Crash, then retry',
    'different-message': 'Same order, new message', 'two-orders-same-sku': 'Two orders, same product',
    'interleaved-retries': 'Two orders + retries', 'payload-conflict': 'Changed order payload',
    'missing-snapshot': 'Missing receipt snapshot', 'unsupported-effect': 'Unsupported effect'
  };
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'text') node.textContent = value;
      else if (key === 'class') node.className = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : String(child));
    return node;
  }
  const status = value => el('span', { class: 'status ' + value, text: signs[value] + ' ' + labels[value] });
  const short = text => String(text).length > 28 ? String(text).slice(0, 25) + '…' : String(text);
  const pretty = value => typeof value === 'string' ? value : JSON.stringify(value);
  function bundledReport(id, name) {
    const text = JSON.parse($(id).textContent);
    return window.RepairImports.decode(new TextEncoder().encode(text), name);
  }
  const reference = bundledReport('example-report', 'repair-example.json');
  const transfer = bundledReport('transfer-report', 'repair-transfer.json');
  let active = reference, source = 'reference', imported = null;
  let caseId = 'interleaved-retries', candidateId = 'overbroad-key';
  let toastTimer = null, importTrigger = null, dialogTrigger = null;

  // Recorded illustration. It always uses the embedded example, never a newly imported report.
  let step = 4, playing = false, replayTimer = null, replayOwner = 'scroll';
  const replayCase = 'interleaved-retries';
  const replayCells = new Map();
  const replayWords = [
    ['0', 'Two valid orders are ready.', 'Both request the same field notes. Each needs its own fulfillment receipt.'],
    ['1', 'A commits. The response is lost.', 'All three handlers create A’s receipt. The configured fault interrupts the response after commit.'],
    ['2', 'B arrives. The product key rejects it.', 'B shares A’s product, not its order ID. The product key raises a payload conflict and creates no receipt.'],
    ['3', 'A retries. The unkeyed handler duplicates it.', 'The product and order keys reuse A’s receipt. Without a key, the retry commits a second receipt.'],
    ['✓', 'The order key protects both orders.', 'B returns in a new message. Only the order key finishes with exactly one receipt for A and one for B.']
  ];
  function buildReplay() {
    $('replay-matrix').setAttribute('role', 'table');
    const heading = el('div', { class: 'replay-row', role: 'row' }, el('div', { role: 'columnheader' }, el('span', { class: 'sr-only', text: 'Order' })));
    for (const candidate of D.candidates(reference.model)) heading.append(el('div', { class: 'replay-colhead', role: 'columnheader' }, policies[candidate.id].title, el('code', { text: policies[candidate.id].key })));
    $('replay-matrix').append(heading);
    for (const [i, orderId] of ['ORDER-A', 'ORDER-B'].entries()) {
      const row = el('div', { class: 'replay-row', role: 'row' }, el('div', { class: 'replay-order', role: 'rowheader', 'aria-label': orderId }, el('small', { 'aria-hidden': 'true', text: 'Order' }), el('span', { 'aria-hidden': 'true', text: orderId.slice(-1) })));
      for (const candidate of D.candidates(reference.model)) {
        const number = el('strong', { class: 'replay-count' });
        const caption = el('span', { class: 'cell-caption' });
        const cell = el('div', { class: 'replay-cell order-' + (i ? 'b' : 'a'), role: 'cell' }, number, caption);
        row.append(cell); replayCells.set(candidate.id + orderId, { cell, number, caption });
      }
      $('replay-matrix').append(row);
    }
    for (let i = 1; i <= 4; i++) {
      const button = el('button', { type: 'button', 'data-step': i, 'aria-label': 'Delivery ' + i + ': ' + replayWords[i][1], text: i });
      button.addEventListener('click', () => { replayOwner = 'manual'; pauseReplay(); step = i; renderReplay(true); });
      $('step-buttons').append(button);
    }
  }
  function renderReplay(announce = false) {
    const replay = D.replay(reference.model, replayCase, step);
    for (const candidate of replay.byCandidate) {
      const view = reference.model.get(replayCase, candidate.id);
      for (const orderId of ['ORDER-A', 'ORDER-B']) {
        const count = step === 4 ? view.counts[orderId] : candidate.counts[orderId];
        const { cell, number, caption } = replayCells.get(candidate.id + orderId);
        const changed = number.textContent !== String(count);
        number.textContent = count === null ? '—' : count;
        number.classList.remove('changed');
        if (changed && !motion.matches) { void number.offsetWidth; number.classList.add('changed'); }
        const rejected = orderId === 'ORDER-B' && candidate.id === 'overbroad-key' && step >= 2;
        const outcome = count === null ? 'incomplete' : count > 1 || rejected ? 'violation' : step === 4 ? 'pass' : 'pending';
        cell.dataset.outcome = outcome;
        caption.textContent = count === null ? 'unknown' : rejected ? 'missing' : count > 1 ? 'duplicate' : count === 1 ? '1 receipt' : 'waiting';
        cell.setAttribute('aria-label', policies[candidate.id].title + ', ' + orderId + ': ' + (count === null ? 'unknown count' : count + (count === 1 ? ' receipt' : ' receipts')) + ', ' + caption.textContent);
      }
    }
    $('stage-progress').textContent = step + ' of 4 deliveries';
    $('step-mark').textContent = replayWords[step][0];
    $('replay-title').textContent = replayWords[step][1];
    $('replay-detail').textContent = replayWords[step][2];
    $('replay-basis').textContent = step === 4 ? 'Final counts checked against independent receipt snapshots.' : 'Recorded events · counts are provisional until the final snapshot.';
    for (const button of $('step-buttons').children) {
      button.setAttribute('aria-pressed', String(Number(button.dataset.step) === step));
      button.classList.toggle('done', Number(button.dataset.step) < step);
    }
    $('replay-back').disabled = step === 0;
    $('replay-next').disabled = step === 4;
    $('replay-toggle').textContent = playing ? 'Ⅱ' : '▷';
    $('replay-toggle').setAttribute('aria-label', playing ? 'Pause recorded replay' : motion.matches ? 'Start recorded replay with manual steps' : step === 4 ? 'Replay recorded deliveries' : 'Play recorded replay');
    $('scroll-mode').textContent = replayOwner === 'scroll' ? 'Scroll linked ↕' : 'Follow scroll ↕';
    $('scroll-mode').setAttribute('aria-pressed', String(replayOwner === 'scroll'));
    $('scroll-mode').title = replayOwner === 'scroll' ? 'Switch to manual replay controls' : 'Link the replay to your current scroll position';
    $('replay').dataset.owner = replayOwner;
    if (announce) $('selection-announcement').textContent = 'Delivery ' + step + ' of 4. ' + replayWords[step][1];
  }
  function pauseReplay() { clearTimeout(replayTimer); replayTimer = null; playing = false; renderReplay(); }
  function scheduleReplay() {
    replayTimer = setTimeout(() => {
      if (!playing || document.hidden) return pauseReplay();
      step += 1;
      if (step >= 4) { step = 4; playing = false; }
      renderReplay(true);
      if (playing) scheduleReplay();
    }, step === 0 ? 850 : 3600);
  }
  function startReplay(reset = false) {
    replayOwner = 'playback';
    clearTimeout(replayTimer);
    if (reset || step === 4) step = 0;
    playing = !motion.matches;
    renderReplay(true);
    if (playing) scheduleReplay();
    else toast('Replay ready. Use the numbered deliveries or arrow buttons.');
  }
  $('hero-play').addEventListener('click', () => { startReplay(true); $('replay').scrollIntoView({ behavior: motion.matches ? 'instant' : 'smooth', block: 'nearest' }); });
  $('replay-toggle').addEventListener('click', () => { replayOwner = 'manual'; playing ? pauseReplay() : startReplay(); });
  $('replay-back').addEventListener('click', () => { replayOwner = 'manual'; pauseReplay(); step = Math.max(0, step - 1); renderReplay(true); });
  $('replay-next').addEventListener('click', () => { replayOwner = 'manual'; pauseReplay(); step = Math.min(4, step + 1); renderReplay(true); });
  $('scroll-mode').addEventListener('click', () => {
    replayOwner = replayOwner === 'scroll' ? 'manual' : 'scroll';
    pauseReplay();
    document.dispatchEvent(new CustomEvent('replayguard:scroll-owner'));
  });
  window.ProposalReplay = Object.freeze({
    setScrollStep(next) {
      if (replayOwner !== 'scroll' || !Number.isInteger(next) || next < 0 || next > 4 || step === next) return;
      clearTimeout(replayTimer); replayTimer = null; playing = false; step = next;
      renderReplay(false);
    },
    chapterCounts(index) {
      return D.replay(reference.model, replayCase, index).byCandidate.map(candidate => ({
        title: policies[candidate.id].title,
        a: index === 4 ? reference.model.get(replayCase, candidate.id).counts['ORDER-A'] : candidate.counts['ORDER-A'],
        b: index === 4 ? reference.model.get(replayCase, candidate.id).counts['ORDER-B'] : candidate.counts['ORDER-B']
      }));
    }
  });
  motion.addEventListener('change', pauseReplay);
  document.addEventListener('visibilitychange', () => { if (document.hidden) pauseReplay(); });
  window.addEventListener('pagehide', () => { pauseReplay(); clearTimeout(toastTimer); });

  function displayCandidate(candidate) { return source === 'reference' && policies[candidate.id] ? policies[candidate.id].title : source === 'transfer' ? 'DispatchDesk adapter' : candidate.title; }
  function displayCase(plan) { return source === 'reference' && caseNames[plan.id] ? caseNames[plan.id] : plan.title; }
  function rebuildSelectors() {
    $('candidate-buttons').replaceChildren(...D.candidates(active.model).map(candidate => {
      const button = el('button', { type: 'button', 'data-candidate': candidate.id, text: displayCandidate(candidate) });
      button.addEventListener('click', () => { candidateId = candidate.id; renderInspector(true); });
      return button;
    }));
    const fragment = document.createDocumentFragment();
    const plans = [...active.model.plans.values()];
    const groups = source === 'reference' ? [
      ['Business regressions', plans.filter(p => !['missing-snapshot', 'unsupported-effect'].includes(p.id))],
      ['Evidence-limit controls', plans.filter(p => ['missing-snapshot', 'unsupported-effect'].includes(p.id))]
    ] : [['Declared cases', plans]];
    for (const [title, group] of groups) {
      if (!group.length) continue;
      fragment.append(el('p', { class: 'case-group-title', text: title }));
      for (const plan of group) {
        const button = el('button', { type: 'button', class: 'case-button', 'data-case': plan.id }, el('span', { class: 'state-dot', 'aria-hidden': 'true' }), el('span', { text: displayCase(plan) }), el('span', { class: 'case-outcome' }));
        button.addEventListener('click', () => { caseId = plan.id; renderInspector(true); });
        fragment.append(button);
      }
    }
    $('case-list').replaceChildren(fragment);
    document.querySelector('.case-note').hidden = source !== 'reference';
  }
  function renderInspector(announce = false) {
    const model = active.model, view = model.get(caseId, candidateId), candidate = model.candidates.get(candidateId);
    const finding = D.describe(view), cov = D.coverage(model, candidateId);
    for (const button of $('candidate-buttons').children) button.setAttribute('aria-pressed', String(button.dataset.candidate === candidateId));
    for (const button of $('case-list').querySelectorAll('button')) {
      const result = model.get(button.dataset.case, candidateId);
      const state = result ? result.status : 'incomplete';
      button.setAttribute('aria-current', String(button.dataset.case === caseId));
      button.setAttribute('aria-label', displayCase(model.plans.get(button.dataset.case)) + ': ' + labels[state]);
      button.firstElementChild.className = 'case-sign ' + state;
      button.firstElementChild.textContent = signs[state];
      button.lastElementChild.textContent = labels[state];
    }
    $('coverage').replaceChildren(...Object.keys(labels).map(state => el('span', {}, el('i', { class: 'state-dot ' + state, 'aria-hidden': 'true' }), el('b', { text: cov[state] }), labels[state])), el('span', { class: 'coverage-scope', text: cov.total + (cov.total === 1 ? ' case' : ' cases') + ' for this handler' }));
    const date = typeof model.report.recordedAt === 'string' ? model.report.recordedAt : typeof model.report.startedAt === 'string' ? model.report.startedAt : null;
    $('source-label').textContent = source === 'reference' ? 'Recorded comparison' : source === 'transfer' ? 'DispatchDesk example' : active.name;
    $('source-context').textContent = source === 'reference' ? 'Bundled local comparison. The opening story always follows this recording; imported files only change this inspector.' : source === 'transfer' ? 'Separately authored synthetic application · five recorded local cases. This is an integration example, not outside-user validation. The opening story still shows the original comparison.' : 'Imported observations · origin unauthenticated. Receipt and source checks assess this supplied file. The opening story still shows the bundled recording.';
    $('source-meta').textContent = (date && !Number.isNaN(Date.parse(date)) ? new Date(date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Date not supplied') + ' · ' + (source === 'reference' || source === 'transfer' ? 'Recorded local Python execution' : 'Imported observations · origin unauthenticated');
    $('source-select').value = source;
    $('case-count').textContent = model.plans.size + (model.plans.size === 1 ? ' case' : ' cases');
    $('case-context').textContent = displayCase(view.plan) + ' · ' + view.plan.deliveries.length + ' deliveries';
    $('verdict').className = 'status ' + view.status;
    $('verdict').textContent = signs[view.status] + ' ' + labels[view.status];
    $('result-title').textContent = finding.title;
    $('result-description').textContent = finding.detail;
    const orders = view.plan.expectedOrders.map(expected => {
      const order = expected.order, count = view.counts[order.orderId];
      const receipts = (view.result.receipts || []).filter(r => r.order.orderId === order.orderId);
      const wrong = receipts.some(r => RepairContract.canonical(r.order) !== RepairContract.canonical(order));
      const state = count === null ? (view.status === 'unresolved' ? 'unresolved' : 'incomplete') : count === 1 && !wrong ? 'pass' : 'violation';
      const card = el('article', { class: 'receipt ' + state, 'aria-label': order.orderId + ' independent receipts' }, el('header', {}, order.orderId, el('span', { class: 'expected', text: 'Expected 1' })), el('div', { class: 'receipt-amount' }, count === null ? '—' : count, el('small', { text: count === null ? 'unknown' : count === 1 ? 'receipt' : 'receipts' })));
      if (count === null) card.append(el('p', { class: 'receipt-missing', text: view.status === 'unresolved' ? 'No supported observation' : 'Snapshot not available' }));
      else if (count === 0) card.append(el('p', { class: 'receipt-missing', text: 'No fulfillment receipt' }));
      else {
        receipts.slice(0, 4).forEach((receipt, index) => {
          const badPayload = RepairContract.canonical(receipt.order) !== RepairContract.canonical(order);
          card.append(el('div', { class: 'receipt-ticket' + (index || badPayload ? ' duplicate' : '') }, el('code', { text: short(receipt.receiptId), title: receipt.receiptId }), el('span', { text: badPayload ? 'Wrong input' : index ? 'Duplicate' : 'Accepted' })));
        });
        if (receipts.length > 4) card.append(el('p', { class: 'receipt-meta', text: '+ ' + (receipts.length - 4) + ' receipts in original JSON' }));
      }
      card.append(el('p', { class: 'receipt-meta', text: order.sku + ' · Qty ' + order.quantity }));
      return card;
    });
    $('order-receipts').replaceChildren(...orders);
    const business = view.checks.filter(c => c.id.startsWith('order:') || c.id === 'receipt-inputs' && c.status !== 'pass');
    business.sort((a, b) => (a.status === 'pass') - (b.status === 'pass'));
    $('business-checks').replaceChildren(...business.map(check => el('div', { class: 'business-check ' + check.status }, el('span', { 'aria-label': labels[check.status], text: signs[check.status] }), el('span', { text: D.checkLabel(check) + (check.observed === null ? ' — unknown' : typeof check.observed === 'number' ? ' — observed ' + check.observed : '') }))));
    const technical = view.checks.filter(check => !business.includes(check)).sort((a, b) => (a.status === 'pass') - (b.status === 'pass'));
    $('check-count').textContent = technical.filter(c => c.status === 'pass').length + ' / ' + technical.length + ' passed';
    $('check-list').replaceChildren(...technical.map(check => el('div', { class: 'check-row' }, el('div', { class: 'check-title' }, status(check.status), el('strong', { text: D.checkLabel(check) })), el('p', { text: check.detail }), el('p', { text: 'Expected: ' + pretty(check.expected) + ' · Observed: ' + pretty(check.observed) }))));
    $('checks-details').open = view.status === 'incomplete' || view.status === 'unresolved' || business.every(check => check.status === 'pass') && technical.some(check => check.status !== 'pass');
    $('delivery-count').textContent = view.result.deliveries.length + ' recorded';
    const eventNames = { 'delivery-start': 'Delivery started', 'delivery-end': 'Delivery finished', 'receipt-accepted': 'Receipt committed', 'receipt-reused': 'Original receipt reused', 'payload-conflict': 'Payload conflict: receipt rejected', 'fault-injected': 'Response lost after receipt commit', 'delivery-completed': 'Handler completed', 'delivery-crashed': 'Configured crash observed', 'delivery-conflict': 'Handler surfaced a conflict', 'delivery-error': 'Handler raised an error' };
    $('delivery-trail').replaceChildren(...view.plan.deliveries.map((delivery, index) => {
      const observed = view.result.deliveries.find(d => d.deliveryId === delivery.deliveryId);
      const events = view.result.events.filter(e => e.deliveryId === delivery.deliveryId);
      const list = el('ol', {}, ...events.map(event => el('li', { text: (Object.hasOwn(eventNames, event.type) ? eventNames[event.type] : event.type) + (typeof event.receiptId === 'string' ? ' · ' + event.receiptId : '') })));
      if (!events.length) list.append(el('li', { text: 'No recorded events for this delivery.' }));
      return el('div', { class: 'trail-group' }, el('h4', { text: (index + 1) + '. ' + delivery.order.orderId + ' · ' + (observed ? observed.outcome : 'not observed') }), el('p', { class: 'detail-note', text: delivery.deliveryId + ' · message ' + delivery.messageId + ' · receive ' + delivery.receiveCount + (delivery.fault === 'after-commit' ? ' · fault after commit' : '') }), list);
    }));
    $('fingerprints').replaceChildren(el('p', { class: 'detail-note', text: 'Adapter: ' + candidate.adapter }), ...Object.entries(candidate.sourceSha256).map(([name, hash]) => el('div', { class: 'fingerprint' }, name, el('code', { text: hash }))), el('p', { class: 'detail-note', text: typeof candidate.sourceHashScope === 'string' ? candidate.sourceHashScope : 'Hashes cover the captured Python source files.' }));
    $('result-boundary').textContent = 'Verdict for this declared case only. The receiver models fulfillment with atomic receipts; it does not establish safety for an external shipment, payment or email.';
    if (announce) $('selection-announcement').textContent = displayCandidate(candidate) + '. ' + displayCase(view.plan) + '. ' + labels[view.status] + '. ' + finding.title;
  }
  function accept(entry, which) {
    const previous = { active, source, caseId, candidateId };
    try {
      active = entry; source = which;
      caseId = entry.model.plans.has('interleaved-retries') ? 'interleaved-retries' : [...entry.model.plans.keys()][0];
      candidateId = entry.model.candidates.has('overbroad-key') ? 'overbroad-key' : D.candidates(entry.model)[0].id;
      rebuildSelectors(); renderInspector(true);
    } catch (error) {
      ({ active, source, caseId, candidateId } = previous);
      rebuildSelectors(); renderInspector();
      throw error;
    }
  }
  $('source-select').addEventListener('change', e => {
    loader.cancel();
    $('report-file').value = '';
    if (e.target.value === 'import' && imported) accept(imported, 'import');
    else if (e.target.value === 'transfer') accept(transfer, 'transfer');
    else accept(reference, 'reference');
    for (const id of ['import-status', 'header-feedback', 'tutorial-feedback']) $(id).hidden = true;
  });

  // Imports never leave the browser. Preserve the previous report on a rejected file.
  function importFeedback(text, error = false) {
    for (const id of ['header-feedback', 'tutorial-feedback']) $(id).hidden = true;
    const localFeedback = importTrigger && importTrigger.closest('.tutorial-panel') ? ['tutorial-feedback'] : importTrigger && importTrigger.closest('.site-head') ? ['header-feedback'] : [];
    for (const id of ['import-status', ...localFeedback]) {
      $(id).textContent = text; $(id).classList.toggle('error', error); $(id).hidden = false;
    }
  }
  for (const button of document.querySelectorAll('[data-import]')) button.addEventListener('click', () => { importTrigger = button; $('report-file').click(); });
  const loader = window.RepairImports.createLoader(entry => accept(entry, 'import'));
  $('report-file').addEventListener('change', async e => {
    const file = e.target.files[0]; if (!file) return;
    const outcome = await loader.load(file);
    if (outcome.status === 'superseded') return;
    $('report-file').value = '';
    if (outcome.status === 'rejected') {
      importFeedback('Could not import: ' + outcome.error.message + ' Your previous report is unchanged.', true);
      return;
    }
    imported = outcome.entry;
    $('source-select').querySelector('[value="import"]').disabled = false;
    $('source-select').value = 'import';
    const totals = Object.fromEntries(Object.keys(labels).map(state => [state, 0]));
    for (const candidate of imported.model.candidates.values()) { const cov = D.coverage(imported.model, candidate.id); for (const state of Object.keys(labels)) totals[state] += cov[state]; }
    const summary = Object.keys(labels).filter(state => totals[state]).map(state => totals[state] + ' ' + labels[state].toLowerCase()).join(' · ');
    importFeedback('Imported ' + file.name + ' — ' + summary + '. Counts checked against supplied observations.');
    $('bench-title').focus({ preventScroll: true });
    $('bench').scrollIntoView({ behavior: 'instant', block: 'start' });
  });
  $('view-json').addEventListener('click', () => { dialogTrigger = document.activeElement; $('raw-json').textContent = active.text; $('json-dialog').showModal(); });
  $('close-json').addEventListener('click', () => $('json-dialog').close());
  $('json-dialog').addEventListener('close', () => { if (dialogTrigger && dialogTrigger.isConnected) dialogTrigger.focus(); });
  $('download-json').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([active.bytes], { type: 'application/json' }));
    const link = el('a', { href: url, download: active.name }); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000); }

  const tutorial = [
    { action: 'Copy the handler and test two orders', command: 'mkdir -p candidate\ncp repair_lab/adapters/business_key.py candidate/adapter.py\npython3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output before.json', result: 'Passed · A: 1 / B: 1 receipt', exit: 'exit 0', file: 'before.json', prompt: 'Inspect one receipt for each order.' },
    { action: 'Change the key to sku, then run again', command: 'python3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output broken.json', result: 'Violation · A: 1 / B: 0 receipts', exit: 'exit 1', file: 'broken.json', prompt: 'Find the valid order the repair rejected.' },
    { action: 'Restore the order key and rerun', command: 'cp repair_lab/adapters/business_key.py candidate/adapter.py\npython3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output restored.json', result: 'Passed · A: 1 / B: 1 receipt', exit: 'exit 0', file: 'restored.json', prompt: 'Keep the same case with your repaired handler.' }
  ];
  function showTutorial(index) {
    const item = tutorial[index];
    for (const button of document.querySelectorAll('[data-tutorial]')) button.setAttribute('aria-pressed', String(Number(button.dataset.tutorial) === index));
    $('code-key').textContent = index === 1 ? 'key=order["sku"]' : 'key=order["orderId"]';
    $('code-key').classList.toggle('broken', index === 1);
    $('tutorial-action').textContent = item.action;
    const commands = item.command.split('\n');
    $('tutorial-command').replaceChildren(...commands.map((command, line) => el('span', { class: 'command-line', text: command + (line === commands.length - 1 ? '' : '\n') })));
    $('edit-instruction').hidden = index !== 1;
    $('edit-instruction').textContent = 'First edit candidate/adapter.py: replace key=order["orderId"] with key=order["sku"]. Save the file, then run this command. Both valid orders share that SKU.';
    $('expected-result').textContent = item.result;
    $('expected-result').classList.toggle('broken', index === 1);
    $('expected-exit').textContent = item.exit;
    $('import-prompt').textContent = item.prompt;
    $('import-filename').textContent = 'Import ' + item.file + ' after the local command finishes.';
    $('tutorial-feedback').hidden = true;
  }
  for (const button of document.querySelectorAll('[data-tutorial]')) button.addEventListener('click', () => showTutorial(Number(button.dataset.tutorial)));
  $('copy-command').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('tutorial-command').textContent); toast('Commands copied. Run them in your extracted kit folder.'); }
    catch { const range = document.createRange(); range.selectNodeContents($('tutorial-command')); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); toast('Commands selected. Copy with your keyboard.'); }
  });
  buildReplay(); renderReplay(); rebuildSelectors(); renderInspector(); showTutorial(0);
})();
