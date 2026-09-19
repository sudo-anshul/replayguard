/* Counts are recomputed from complete recorded ledger reads. Full execution
 * verdicts come from the Python verifier run during the deterministic build.
 * The browser checks the raw file hash before calling this display adapter.
 */
(function (root) {
  'use strict';
  const candidates = ['no-key', 'sku-key', 'order-key'];
  const states = new Set(['passed', 'violation', 'incomplete', 'unresolved']);
  const canonical = value => {
    if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
    return JSON.stringify(value);
  };
  function inspect(evidence, view) {
    if (!evidence || evidence.kind !== 'replayguard-aws-key-scope-report' || evidence.schemaVersion !== 2 || evidence.provenance !== 'aws') throw new Error('Expected the recorded AWS key-scope report, schema v2.');
    if (!view || view.kind !== 'replayguard-aws-key-scope-web-view' || view.schemaVersion !== 1 || !view.verification) throw new Error('The build-time verification record is unavailable.');
    const orders = evidence.case && evidence.case.orders;
    if (!Array.isArray(orders) || orders.length !== 2 || canonical(evidence.case.candidates) !== canonical(candidates) || orders.some(order => !order || typeof order.orderId !== 'string' || typeof order.sku !== 'string' || !Number.isInteger(order.quantity))) throw new Error('The two-order comparison is malformed.');
    if (!Array.isArray(evidence.events) || evidence.events.length > 2000 || !Array.isArray(evidence.ledgerObservations) || evidence.ledgerObservations.length > 400) throw new Error('Recorded observation bounds are invalid.');
    if (view.verification.runId && view.verification.runId !== evidence.runId) throw new Error('The verifier result belongs to a different run.');
    const results = view.verification.candidateResults || [];
    let mismatch = false;
    const rows = candidates.map(candidate => {
      const raw = evidence.receipts && evidence.receipts[candidate];
      const reads = evidence.ledgerObservations.filter(read => read && read.candidate === candidate && read.consistent === true);
      const recordedRead = evidence.collection && evidence.collection.lastLedgerReadAt && evidence.collection.lastLedgerReadAt[candidate];
      const complete = Array.isArray(raw) && raw.length <= 500 && reads.length > 0 && canonical(reads.at(-1).items) === canonical(raw) &&
        typeof reads.at(-1).observedAt === 'string' && Number.isFinite(Date.parse(reads.at(-1).observedAt)) && reads.at(-1).observedAt === recordedRead;
      const counts = Object.fromEntries(orders.map(order => [order.orderId, complete ? raw.filter(receipt => receipt && canonical(receipt.order) === canonical(order)).length : null]));
      const result = results.find(item => item.candidate === candidate);
      const disagreement = !!result && canonical(result.receiptCounts) !== canonical(counts);
      mismatch ||= disagreement;
      const status = disagreement ? 'unresolved' : result && states.has(result.status) ? result.status : 'incomplete';
      const events = evidence.events.filter(event => event && event.candidate === candidate);
      return { candidate, counts, status, complete, receipts: complete ? raw : [], events, assertions: result && Array.isArray(result.assertions) ? result.assertions : [], disagreement };
    });
    const cleanup = evidence.cleanup || {}, deployment = evidence.deployment || {};
    const confirmed = cleanup.status === 'deleted' && cleanup.verified === true && ['DELETE_COMPLETE', 'absent'].includes(cleanup.lastStackStatus) &&
      !!cleanup.stackArn && cleanup.stackArn === deployment.stackArn;
    const rawCleanup = confirmed ? 'passed' : ['deleted', 'failed', 'unconfirmed'].includes(cleanup.status) ? 'unresolved' : 'incomplete';
    const cleanupMismatch = rawCleanup !== view.verification.operationalStatus;
    return {
      orders, rows,
      experimentStatus: mismatch ? 'unresolved' : states.has(view.verification.experimentStatus) ? view.verification.experimentStatus : 'incomplete',
      operationalStatus: cleanupMismatch ? 'unresolved' : rawCleanup,
      assertions: Array.isArray(view.verification.assertions) ? view.verification.assertions : [],
      mismatch: mismatch || cleanupMismatch
    };
  }
  root.AwsKeyScopeData = Object.freeze({ inspect, canonical });
})(typeof window !== 'undefined' ? window : globalThis);
