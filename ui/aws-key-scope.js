(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const names = { 'no-key': 'No key', 'sku-key': 'Product key', 'order-key': 'Order key' };
  const labels = { passed: 'Passed', violation: 'Violation', incomplete: 'Incomplete', unresolved: 'Unresolved' };
  const signs = { passed: '✓', violation: '×', incomplete: '◌', unresolved: '?' };
  let model = null, selected = 'no-key';
  const view = JSON.parse($('aws-key-scope-view').textContent);
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs)) {
      if (name === 'text') node.textContent = value;
      else if (name === 'class') node.className = value;
      else node.setAttribute(name, value);
    }
    for (const child of children.flat()) if (child !== undefined && child !== null) node.append(child instanceof Node ? child : String(child));
    return node;
  }
  function badge(state, node) {
    const item = node || document.createElement('span');
    item.className = 'status ' + (state === 'passed' ? 'pass' : state);
    item.textContent = signs[state] + ' ' + labels[state];
    return item;
  }
  function date(value, timeOnly = false) {
    if (typeof value !== 'string' || !Number.isFinite(Date.parse(value))) return 'Not supplied';
    return new Date(value).toLocaleString('en-GB', timeOnly ? { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC', hour12: false } : { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC', hour12: false }) + (timeOnly ? '' : ' UTC');
  }
  function link(id, file, label) {
    const node = $(id);
    node.href = './' + file.path + '?v=' + file.sha256;
    node.setAttribute('aria-disabled', 'false');
    node.replaceChildren(label, el('span', { 'aria-hidden': 'true', text: id === 'scope-archive' ? '↓' : '↗' }));
    if (id === 'scope-archive') node.download = file.path;
    else { node.target = '_blank'; node.rel = 'noopener'; }
  }
  function trail() {
    for (const button of document.querySelectorAll('[data-scope-candidate]')) button.setAttribute('aria-pressed', String(button.dataset.scopeCandidate === selected));
    if (!model) return;
    const row = model.rows.find(item => item.candidate === selected);
    const stages = {
      received: 'Worker received the SQS message', accepted: 'Receiver committed a new receipt',
      fault_injected: 'Response failed after receipt commit', provider_failed: 'Worker observed provider failure',
      failed: 'Worker invocation failed', reused: 'Receiver reused the original receipt',
      fulfillment_succeeded: 'Worker received fulfillment success', business_rejected: 'Worker rejected the conflicting order',
      payload_conflict: 'Receiver rejected the changed payload', completed: 'Worker completed'
    };
    $('scope-trace-note').textContent = names[selected] + ' · ' + row.events.length + ' captured events · ' + labels[row.status] + ' business result. Times below are UTC.';
    $('scope-events').replaceChildren(...row.events.map(event => {
      const eventDate = Number.isInteger(event.eventTimestamp) ? new Date(event.eventTimestamp) : null;
      const stamp = eventDate && Number.isFinite(eventDate.getTime()) ? eventDate.toISOString() : event.timestamp;
      const detail = [event.orderId, typeof event.receiveCount === 'number' ? 'receive ' + event.receiveCount : null, event.outcome, event.receiptId ? 'receipt ' + event.receiptId : null].filter(Boolean).join(' · ');
      return el('li', { class: /fault|fail|conflict|reject/.test(event.stage) ? 'event-fault' : '' },
        el('time', { datetime: stamp || '', text: date(stamp, true) }),
        el('div', {}, el('strong', { text: Object.hasOwn(stages, event.stage) ? stages[event.stage] : typeof event.stage === 'string' ? event.stage : 'Recorded event' }), el('p', { text: detail })),
        el('span', { class: 'event-source', text: event.source || 'source not supplied' }));
    }));
    if (!row.events.length) $('scope-events').append(el('li', { class: 'scope-empty', text: 'No captured events for this handler. No execution is inferred.' }));
  }
  function render(evidence) {
    model = window.AwsKeyScopeData.inspect(evidence, view);
    badge(model.experimentStatus, $('experiment-status'));
    $('experiment-explanation').textContent = model.experimentStatus === 'passed' ? 'Required fault, retry, receipt and observation checks passed for this bounded run.' : model.experimentStatus === 'unresolved' ? 'A contradiction prevents a resolved experiment result. Inspect the checks below.' : 'Required evidence is missing or unfinished. Available counts do not establish a complete experiment.';
    const totals = { passed: 0, violation: 0, incomplete: 0, unresolved: 0 };
    model.rows.forEach(row => { totals[row.status] += 1; badge(row.status, $('candidate-' + row.candidate).firstElementChild); });
    $('business-summary').textContent = Object.keys(totals).filter(state => totals[state]).map(state => totals[state] + ' ' + (state === 'passed' ? 'passed' : state === 'violation' ? (totals[state] === 1 ? 'violation' : 'violations') : state)).join(' · ');
    badge(model.operationalStatus, $('cleanup-status'));
    $('cleanup-explanation').textContent = model.operationalStatus === 'passed' ? 'The captured cleanup record confirms deletion of this experimental stack. The viewer is hosted separately.' : model.operationalStatus === 'unresolved' ? 'Experimental stack deletion is unconfirmed or contradictory. This remains an operational task.' : 'Complete deletion evidence has not been supplied.';
    $('scope-date').textContent = date(evidence.recordedAt);
    $('scope-region').textContent = typeof evidence.region === 'string' ? evidence.region : 'Not supplied';
    $('scope-run').textContent = typeof evidence.runId === 'string' ? evidence.runId : 'Not supplied';
    $('scope-counts').replaceChildren(...model.orders.map(order => el('tr', {},
      el('th', { scope: 'row' }, order.orderId, el('small', { text: order.sku + ' · quantity ' + order.quantity + ' · expected 1' })),
      ...model.rows.map(row => {
        const count = row.counts[order.orderId];
        const state = count === null ? 'incomplete' : count === 1 ? 'passed' : 'violation';
        return el('td', { 'data-result': state }, count === null ? '—' : count, el('small', { text: count === null ? 'snapshot unavailable' : count === 1 ? '1 receipt' : count === 0 ? 'no receipt observed' : 'duplicate receipts' }));
      }))));
    const checks = [...model.assertions].sort((a, b) => (a.status === 'passed') - (b.status === 'passed'));
    $('scope-check-count').textContent = checks.filter(check => check.status === 'passed').length + ' / ' + checks.length + ' passed';
    $('scope-checks').replaceChildren(...checks.map(check => el('div', { class: 'scope-check' }, badge(labels[check.status] ? check.status : 'incomplete'), el('strong', { text: check.id }), el('p', { text: check.detail || 'No detail supplied.' }))));
    $('scope-check-details').open = model.experimentStatus !== 'passed';
    $('scope-notice').className = 'scope-notice ' + (model.mismatch ? 'error' : 'checked');
    $('scope-notice').textContent = model.mismatch ? 'Browser counts or cleanup facts disagree with the generated verification view. This result is unresolved.' : 'Recorded AWS export · original file SHA-256 matched · receipt counts recomputed from recorded ledger queries. Full execution checks were regenerated by the offline verifier during the site build. Export origin remains unauthenticated.';
    trail();
  }
  for (const button of document.querySelectorAll('[data-scope-candidate]')) button.addEventListener('click', () => { selected = button.dataset.scopeCandidate; trail(); });
  if (view.archive) link('scope-archive', view.archive, 'Download this AWS regression');
  else if (view.archiveIssue) $('scope-archive').title = view.archiveIssue;
  if (!view.report) {
    $('scope-notice').textContent = 'Incomplete — the new AWS recording has not been attached. Receipt counts, business results and cleanup remain unknown. The earlier dated experiment is available from the navigation.';
    return;
  }
  link('scope-report', view.report, 'Original report JSON');
  $('scope-file-hash').textContent = 'Original report SHA-256\n' + view.report.sha256;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  window.addEventListener('pagehide', () => controller.abort(), { once: true });
  (async () => {
    try {
      if (!crypto.subtle) throw new Error('Open this page over HTTPS or localhost to check the evidence hash.');
      const response = await fetch('./' + view.report.path + '?v=' + view.report.sha256, { signal: controller.signal, cache: 'no-cache' });
      if (!response.ok) throw new Error('The recorded report could not be loaded.');
      const bytes = await response.arrayBuffer();
      if (bytes.byteLength > 8 * 1024 * 1024) throw new Error('The recorded report exceeds the 8 MiB viewing limit.');
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
      if (hash !== view.report.sha256) throw new Error('Report bytes differ from the file used by the build-time verifier.');
      const evidence = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
      render(evidence);
    } catch (error) {
      model = null;
      badge('incomplete', $('experiment-status'));
      badge('incomplete', $('cleanup-status'));
      for (const candidate of Object.keys(names)) badge('incomplete', $('candidate-' + candidate).firstElementChild);
      $('business-summary').textContent = 'Not established';
      $('experiment-explanation').textContent = 'The report could not be fully displayed and checked.';
      $('cleanup-explanation').textContent = 'Cleanup facts could not be fully checked.';
      $('scope-counts').replaceChildren(el('tr', {}, el('th', { scope: 'row', text: 'Receipt snapshot' }), ...Object.keys(names).map(() => el('td', {}, '—', el('small', { text: 'not established' })))));
      $('scope-notice').className = 'scope-notice error';
      $('scope-notice').textContent = 'Incomplete — ' + (error.name === 'AbortError' ? 'The report read did not finish.' : error.message) + ' No passing result is inferred.';
    } finally { clearTimeout(timeout); }
  })();
})();
