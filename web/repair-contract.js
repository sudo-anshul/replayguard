/* Browser-side consistency checks for the bounded repair lab. No execution or origin authentication. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RepairContract = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const STATES = ['pass', 'violation', 'incomplete', 'unresolved'];
  const rank = { pass: 0, incomplete: 1, violation: 2, unresolved: 3 };
  const canonical = value => JSON.stringify(normalize(value));
  function normalize(value) {
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, normalize(value[k])]));
    return value;
  }
  function fail(message) { throw new Error(message); }
  function object(value, label) { if (!value || typeof value !== 'object' || Array.isArray(value)) fail(label + ' must be an object.'); }
  function string(value, label, max = 600) { if (typeof value !== 'string' || !value.length || value.length > max) fail(label + ' must be a nonempty string of at most ' + max + ' characters.'); }
  function array(value, label, max, min = 0) { if (!Array.isArray(value) || value.length > max || value.length < min) fail(label + ' has an unsupported size.'); }
  function boolean(value, label) { if (typeof value !== 'boolean') fail(label + ' must be true or false.'); }
  function integer(value, label, min = 0, max = 10000) { if (!Number.isInteger(value) || value < min || value > max) fail(label + ' is outside the supported range.'); }
  function unique(values, label) { if (new Set(values).size !== values.length) fail(label + ' contains duplicate identities.'); }
  function attributes(value, depth = 0, budget = { left: 4096 }) {
    if (--budget.left < 0 || depth > 32) fail('Order attributes exceed supported structural bounds.');
    if (typeof value === 'number' && (!Number.isFinite(value) || (Number.isInteger(value) && !Number.isSafeInteger(value)))) fail('Order attributes contain an unsupported JSON number.');
    if (value && typeof value === 'object') Object.values(value).forEach(child => attributes(child, depth + 1, budget));
  }
  function order(value) {
    object(value, 'Order'); string(value.orderId, 'Order ID', 256); string(value.sku, 'SKU', 256); integer(value.quantity, 'Quantity', 1, 1000000);
    if (value.attributes !== undefined) { object(value.attributes, 'Order attributes'); attributes(value.attributes); if (canonical(value.attributes).length > 12000) fail('Order attributes are too large.'); }
  }
  function validateCase(plan) {
    object(plan, 'Case'); string(plan.id, 'Case ID', 160); string(plan.title, 'Case title', 300); if (typeof plan.description !== 'string' || plan.description.length > 2000) fail('Invalid case description.');
    if (!['receiver-owned-receipt', 'unsupported-external'].includes(plan.effectModel)) fail('Unsupported effect model.'); if (!['independent-ledger', 'missing'].includes(plan.observation)) fail('Unsupported observation mode.');
    array(plan.expectedOrders, 'Expected orders', 8, plan.effectModel === 'receiver-owned-receipt' ? 1 : 0); array(plan.deliveries, 'Declared deliveries', 8, plan.effectModel === 'receiver-owned-receipt' ? 1 : 0);
    for (const item of plan.expectedOrders) { object(item, 'Expected order'); order(item.order); if (item.count !== 1) fail('This viewer supports exactly one receipt per business order.'); }
    unique(plan.expectedOrders.map(x => x.order.orderId), 'Expected orders');
    for (const d of plan.deliveries) {
      object(d, 'Declared delivery'); string(d.deliveryId, 'Delivery ID', 160); string(d.messageId, 'Message ID', 256); integer(d.receiveCount, 'Receive count', 1, 1000000); order(d.order);
      if (!['none', 'after-commit'].includes(d.fault) || !['complete', 'crash', 'conflict'].includes(d.expect)) fail('Unsupported delivery condition.');
      if ((d.fault === 'after-commit') !== (d.expect === 'crash')) fail('Crash expectation and failpoint must agree.');
    }
    unique(plan.deliveries.map(d => d.deliveryId), 'Declared deliveries');
  }
  function assess(result, plan) {
    const checks = [];
    const add = (id, status, expected, observed, detail) => checks.push({ id, status, expected, observed, detail });
    const receipts = result.receipts;
    const expected = new Map(plan.expectedOrders.map(item => [item.order.orderId, item]));
    const counts = Object.fromEntries(plan.expectedOrders.map(item => [item.order.orderId, receipts === null ? null : receipts.filter(r => r.order.orderId === item.order.orderId).length]));
    if (plan.effectModel !== 'receiver-owned-receipt') {
      add('supported-effect', 'unresolved', 'receiver-owned-receipt', plan.effectModel, 'An external effect without the supported atomic receiver contract was not tested.');
      return { status: 'unresolved', checks, counts, result, plan };
    }
    add('source-loaded', result.execution.imported && result.execution.built ? 'pass' : 'incomplete', 'Adapter loaded and built', { loaded: result.execution.imported, built: result.execution.built }, 'The runner must load the adapter and obtain a callable handler.');
    add('source-unchanged', result.execution.sourceUnchanged ? 'pass' : 'incomplete', true, result.execution.sourceUnchanged, 'Captured candidate source must remain unchanged during execution.');
    add('bounded-local-execution', result.blockedOperationCount ? 'unresolved' : 'pass', 0, result.blockedOperationCount, 'A blocked operation invalidates this trusted-code local execution.');
    const actual = new Map(result.deliveries.map(d => [d.deliveryId, d]));
    add('schedule-executed', result.execution.completedSchedule && plan.deliveries.length === result.deliveries.length && plan.deliveries.every(d => actual.has(d.deliveryId) && actual.get(d.deliveryId).outcome !== 'not-run') ? 'pass' : 'incomplete', plan.deliveries.length, result.deliveries.filter(d => d.outcome !== 'not-run').length, 'Every declared bounded delivery must have an execution observation.');
    add('independent-snapshot', receipts === null ? 'incomplete' : 'pass', 'An independent receipt snapshot', receipts === null ? 'Unavailable' : receipts.length + ' receipts', 'A missing snapshot is unknown, not an empty ledger.');
    if (receipts !== null) {
      for (const item of plan.expectedOrders) {
        const count = counts[item.order.orderId];
        add('order:' + item.order.orderId, count === 1 && receipts.filter(r => r.order.orderId === item.order.orderId).every(r => canonical(r.order) === canonical(item.order)) ? 'pass' : 'violation', 1, count, count === 0 ? 'This valid order has no receipt after the declared schedule.' : count > 1 ? 'This business order produced duplicate receipts.' : 'This order has exactly one independently observed receipt.');
      }
      const wrong = receipts.filter(r => !expected.has(r.order.orderId) || canonical(r.order) !== canonical(expected.get(r.order.orderId).order));
      add('receipt-inputs', wrong.length ? 'violation' : 'pass', 'Only declared order payloads', wrong.map(r => r.receiptId), 'An unrequested order or changed fulfillment payload is a contract violation.');
      const byId = new Map(receipts.map(r => [r.receiptId, r]));
      const links = [];
      for (const r of receipts) {
        const accepting = actual.get(r.acceptedDeliveryId);
        if (!accepting || !accepting.acceptedReceiptIds.includes(r.receiptId) ) links.push(r.receiptId);
      }
      for (const d of result.deliveries) {
        for (const id of d.acceptedReceiptIds) {
          const r = byId.get(id);
          if (!r || r.acceptedDeliveryId !== d.deliveryId ) links.push(id);
        }
        for (const id of d.reusedReceiptIds) {
          const r = byId.get(id);
          const acceptedIndex = r ? result.deliveries.findIndex(x => x.deliveryId === r.acceptedDeliveryId) : -1;
          const currentIndex = result.deliveries.indexOf(d);
          if (!r  || acceptedIndex > currentIndex || acceptedIndex < 0) links.push(id);
        }
      }
      add('receipt-delivery-links', links.length ? 'unresolved' : 'pass', 'Every accepted/reused receipt links to its delivery and snapshot', [...new Set(links)], 'Ledger and delivery observations must agree in both directions.');
    }
    for (const planned of plan.deliveries) {
      const d = actual.get(planned.deliveryId);
      if (!d) { add('delivery:' + planned.deliveryId, 'incomplete', planned.expect, 'Missing', 'No execution observation for this delivery.'); continue; }
      let status;
      if (planned.expect === 'complete') status = d.outcome === 'completed' ? 'pass' : d.outcome === 'conflict' ? 'violation' : 'incomplete';
      else if (planned.expect === 'conflict') status = d.acceptedReceiptIds.length > 0 || d.outcome === 'completed' ? 'violation' : d.outcome === 'conflict' ? 'pass' : 'incomplete';
      else {
        const witness = receipts !== null && d.acceptedReceiptIds.some(id => {
          const accepted = result.events.find(e => e.type === 'receipt-accepted' && e.deliveryId === d.deliveryId && e.receiptId === id);
          const injected = result.events.find(e => e.type === 'fault-injected' && e.deliveryId === d.deliveryId && e.receiptId === id);
          return receipts.some(r => r.receiptId === id && r.acceptedDeliveryId === d.deliveryId) && accepted && injected && accepted.index < injected.index;
        });
        status = d.outcome === 'crashed' && d.faultInjected && witness ? 'pass' : 'incomplete';
      }
      add('delivery:' + planned.deliveryId, status, planned.expect, d.outcome, planned.expect === 'crash' ? 'The configured crash must follow a newly committed receipt, before the response returns.' : planned.expect === 'conflict' ? 'Changed inputs must be rejected without creating an additional effect.' : 'A valid delivery must complete; rejecting a different legitimate order is a violation.');
    }
    for (const error of result.errors) add('execution:' + error.phase, 'incomplete', 'No unexpected execution error', error.type + ': ' + error.message, 'The runner reported an execution problem.');
    const status = checks.reduce((best, c) => rank[c.status] > rank[best] ? c.status : best, 'pass');
    return { status, checks, counts, result, plan };
  }
  function validate(report) {
    object(report, 'Report');
    if (report.schemaVersion !== 2 || report.kind !== 'replayguard-repair-report' || report.provenance !== 'local-execution') fail('Choose a repair-lab report generated by scripts/test_repair.py. Historical AWS and version 1 reports belong in the original comparison.');
    array(report.candidates, 'Candidates', 12, 1); array(report.cases, 'Cases', 32, 1); array(report.results, 'Results', 384, 1);
    for (const c of report.candidates) {
      object(c, 'Candidate'); string(c.id, 'Candidate ID', 128); string(c.title, 'Candidate title', 300); string(c.adapter, 'Adapter path', 1000); object(c.sourceSha256, 'Source fingerprints');
      if (Object.keys(c.sourceSha256).length > 100) fail('Too many source files.');
      for (const [name, hash] of Object.entries(c.sourceSha256)) { string(name, 'Source path', 1000); if (typeof hash !== 'string' || !/^[a-f0-9]{64}$/i.test(hash)) fail('Invalid source fingerprint.'); }
    }
    report.cases.forEach(validateCase); unique(report.candidates.map(c => c.id), 'Candidates'); unique(report.cases.map(c => c.id), 'Cases');
    const candidates = new Map(report.candidates.map(c => [c.id, c])), plans = new Map(report.cases.map(c => [c.id, c]));
    const results = new Map();
    for (const r of report.results) {
      object(r, 'Result'); if (!candidates.has(r.candidateId) || !plans.has(r.caseId)) fail('A result refers to an unknown candidate or case.');
      const identity = r.caseId + '\u0000' + r.candidateId; if (results.has(identity)) fail('Duplicate candidate/case result.');
      const plan = plans.get(r.caseId); if (canonical(r.expectedOrders) !== canonical(plan.expectedOrders)) fail('Result expectations differ from the declared case.');
      if (!STATES.includes(r.status)) fail('Unsupported result status.');
      object(r.execution, 'Execution'); ['imported', 'built', 'sourceUnchanged', 'snapshotComplete', 'completedSchedule'].forEach(k => boolean(r.execution[k], 'Execution ' + k));
      if (r.execution.built && !r.execution.imported) fail('A built candidate is marked as not imported.');
      if (plan.observation === 'missing' && r.receipts !== null) fail('A withheld observer cannot supply a snapshot.');
      if (r.execution.snapshotComplete !== (r.receipts !== null)) fail('Snapshot availability contradicts its execution flag.');
      integer(r.blockedOperationCount, 'Blocked operation count', 0, 100000);
      array(r.deliveries, 'Observed deliveries', 8); array(r.events, 'Events', 512); array(r.errors, 'Execution errors', 64);
      unique(r.deliveries.map(d => d.deliveryId), 'Observed deliveries');
      for (const d of r.deliveries) {
        object(d, 'Observed delivery'); const p = plan.deliveries.find(x => x.deliveryId === d.deliveryId); if (!p) fail('An undeclared delivery appears in the result.');
        if (d.messageId !== p.messageId || d.receiveCount !== p.receiveCount || canonical(d.order) !== canonical(p.order) || d.fault !== p.fault || d.expect !== p.expect) fail('Observed delivery input differs from the declared plan.');
        if (!['completed', 'crashed', 'conflict', 'error', 'timeout', 'not-run'].includes(d.outcome)) fail('Unsupported delivery outcome.');
        boolean(d.faultInjected, 'Fault observation'); boolean(d.conflictObserved, 'Conflict observation'); boolean(d.attempted, 'Delivery attempt');
        if (d.attempted === (d.outcome === 'not-run')) fail('Delivery attempt and outcome contradict each other.');
        if (d.faultInjected && d.fault !== 'after-commit') fail('A fault was observed where the plan configured none.');
        for (const key of ['acceptedReceiptIds', 'reusedReceiptIds']) { array(d[key], key, 64); d[key].forEach(id => string(id, 'Receipt ID', 256)); }
        unique(d.acceptedReceiptIds, 'Accepted receipt IDs');
      }
      if (r.execution.completedSchedule !== (r.deliveries.length === plan.deliveries.length && r.deliveries.length > 0 && r.deliveries.every(d => d.attempted))) fail('Schedule completion contradicts the delivery observations.');
      if (r.receipts !== null) {
        array(r.receipts, 'Receipt snapshot', 64); unique(r.receipts.map(x => x.receiptId), 'Receipt snapshot');
        for (const receipt of r.receipts) { object(receipt, 'Receipt'); string(receipt.receiptId, 'Receipt ID', 256); string(receipt.acceptedDeliveryId, 'Accepting delivery', 160); order(receipt.order); if (receipt.key !== null) string(receipt.key, 'Receipt key', 256); }
      }
      for (const error of r.errors) { object(error, 'Execution error'); string(error.phase, 'Error phase', 128); string(error.type, 'Error type', 256); if (typeof error.message !== 'string' || error.message.length > 10000) fail('Invalid error message.'); if (error.status !== undefined && !STATES.includes(error.status)) fail('Invalid error status.'); }
      r.events.forEach((event, index) => {
        object(event, 'Event'); string(event.type, 'Event type', 128); if (event.index !== index) fail('Event indices are not a continuous sequence.');
        if (event.deliveryId !== null && event.deliveryId !== undefined && !plan.deliveries.some(d => d.deliveryId === event.deliveryId)) fail('Event refers to an undeclared delivery.');
        const d = r.deliveries.find(x => x.deliveryId === event.deliveryId);
        if (['receipt-accepted', 'receipt-reused', 'fault-injected', 'payload-conflict'].includes(event.type) && !d) fail('Effect event has no observed delivery.');
        if (event.type === 'fault-injected' && (event.fault !== 'after-commit' || !d.faultInjected)) fail('Injected-fault event contradicts its delivery flag.');
        if (event.type === 'payload-conflict' && !d.conflictObserved) fail('Receiver conflict event contradicts its delivery flag.');
        if (event.type === 'receipt-accepted' || event.type === 'receipt-reused') {
          const list = event.type === 'receipt-accepted' ? d.acceptedReceiptIds : d.reusedReceiptIds;
          if (!list.includes(event.receiptId)) fail('Effect event has no matching receipt reference in the delivery.');
          if (r.receipts !== null) {
            const receipt = r.receipts.find(x => x.receiptId === event.receiptId);
            if (!receipt || (event.order && canonical(event.order) !== canonical(receipt.order)) || (event.key !== undefined && event.key !== receipt.key)) fail('Effect event contradicts the independent receipt snapshot.');
          }
        }
      });
      for (const d of r.deliveries) {
        const events = r.events.filter(e => e.deliveryId === d.deliveryId);
        for (const [type, ids] of [['receipt-accepted', d.acceptedReceiptIds], ['receipt-reused', d.reusedReceiptIds]]) {
          if (canonical(events.filter(e => e.type === type).map(e => e.receiptId)) !== canonical(ids)) fail('Receipt references and their ordered effect events disagree.');
        }
        const faults = events.filter(e => e.type === 'fault-injected');
        if (Boolean(faults.length) !== d.faultInjected || faults.length > 1) fail('Fault observation and injection events disagree.');
        for (const fault of faults) {
          if (!d.acceptedReceiptIds.includes(fault.receiptId) || !events.some(e => e.type === 'receipt-accepted' && e.receiptId === fault.receiptId && e.index < fault.index)) fail('An injected fault has no preceding committed receipt.');
        }
      }
      const derived = assess(r, plan);
      if (derived.status !== r.status) fail('Reported ' + r.status + ' contradicts the observations (' + derived.status + ') for ' + r.candidateId + ' / ' + r.caseId + '.');
      results.set(identity, derived);
    }
    if (results.size !== candidates.size * plans.size) fail('The report is missing a candidate/case result. Generate a complete report for the selected candidates and cases.');
    object(report.summary, 'Summary');
    const counts = Object.fromEntries(STATES.map(state => [state, [...results.values()].filter(r => r.status === state).length]));
    const aggregate = [...results.values()].reduce((best, r) => rank[r.status] > rank[best] ? r.status : best, 'pass');
    const exitCodes = { pass: 0, violation: 1, incomplete: 2, unresolved: 3 };
    if (report.summary.status !== aggregate || report.summary.exitCode !== exitCodes[aggregate] || canonical(report.summary.counts) !== canonical(counts)) fail('Summary claims contradict the individual observations.');
    return { report, candidates, plans, results, get: (caseId, candidateId) => results.get(caseId + '\u0000' + candidateId) };
  }
  return { validate, assess, canonical, STATES };
});
