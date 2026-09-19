/* ReplayGuard proposal: presentation helpers over the unchanged repair contract.
 * This file neither runs a handler nor authenticates an imported report's origin.
 * Replay counts come from recorded events. Final assertions use the observer snapshot.
 */
(function (root) {
  'use strict';

  const POLICY_ORDER = ['no-key', 'overbroad-key', 'business-key'];
  const EFFECT_EVENTS = new Set(['receipt-accepted', 'receipt-reused', 'payload-conflict', 'fault-injected']);

  function create(report) {
    if (!root.RepairContract || typeof root.RepairContract.validate !== 'function') {
      throw new Error('Load repair-contract.js before the proposal data helper.');
    }
    return root.RepairContract.validate(report);
  }

  function candidates(model) {
    return [...model.candidates.values()].sort((a, b) => {
      const ai = POLICY_ORDER.indexOf(a.id), bi = POLICY_ORDER.indexOf(b.id);
      return (ai < 0 ? POLICY_ORDER.length : ai) - (bi < 0 ? POLICY_ORDER.length : bi);
    });
  }

  function coverage(model, candidateId) {
    if (!model.candidates.has(candidateId)) throw new Error('Choose a candidate in this report.');
    const counts = { pass: 0, violation: 0, incomplete: 0, unresolved: 0, total: 0 };
    for (const plan of model.plans.values()) {
      const view = model.get(plan.id, candidateId);
      counts[view ? view.status : 'incomplete'] += 1;
      counts.total += 1;
    }
    return counts;
  }

  function describe(view) {
    if (!view) return { title: 'No result to inspect.', detail: 'Choose a case and candidate with recorded evidence.' };
    const failedOrders = view.checks.filter(check => check.id.startsWith('order:') && check.status === 'violation');
    const missing = failedOrders.filter(check => check.observed === 0);
    const duplicated = failedOrders.filter(check => typeof check.observed === 'number' && check.observed > 1);
    const names = checks => checks.map(check => check.id.slice(6)).join(', ');
    if (view.status === 'unresolved') {
      if (view.plan.effectModel !== 'receiver-owned-receipt') {
        return { title: 'This effect is outside the contract.', detail: 'The receiver-owned receipt model does not establish safety for this external effect. No passing result is claimed.' };
      }
      return { title: 'The evidence cannot support a verdict.', detail: 'An execution boundary or receipt-link check is unresolved. Inspect that check before relying on the result.' };
    }
    if (view.status === 'incomplete') {
      if (view.result.receipts === null) {
        return { title: 'The receipt snapshot is missing.', detail: 'Without an independent observer snapshot, handler events alone cannot establish receipt counts. Counts remain unknown.' };
      }
      return { title: 'The declared test did not finish cleanly.', detail: 'A required delivery, crash witness or execution check is incomplete. The available receipts do not establish a complete pass.' };
    }
    if (view.status === 'violation') {
      if (missing.length && duplicated.length) return { title: 'Orders were lost and duplicated.', detail: 'Missing receipts: ' + names(missing) + '. Duplicate receipts: ' + names(duplicated) + '.' };
      if (missing.length) return { title: missing.length === 1 ? 'A valid order disappeared.' : 'Valid orders disappeared.', detail: names(missing) + ' has no independent receipt after the declared deliveries. Preventing retries must not discard a different valid order.' };
      if (duplicated.length) return { title: duplicated.length === 1 ? 'An order was fulfilled more than once.' : 'Orders were fulfilled more than once.', detail: names(duplicated) + ' produced duplicate receipts in the independent snapshot.' };
      const inputs = view.checks.find(check => check.id === 'receipt-inputs' && check.status === 'violation');
      if (inputs) return { title: 'A receipt does not match the order.', detail: 'The snapshot contains an unrequested order or a changed fulfillment payload.' };
      return { title: 'A delivery broke the contract.', detail: 'A valid delivery was rejected, or a changed payload was accepted. Inspect the failed assertion and its receipt evidence.' };
    }
    const total = view.plan.expectedOrders.length;
    return {
      title: total === 1 ? 'One order. One correct receipt.' : 'Every order. One correct receipt.',
      detail: 'The independent snapshot contains exactly one matching receipt for ' + (total === 1 ? 'the declared business order' : 'each of the ' + total + ' declared business orders') + '. All required checks in this bounded case passed.'
    };
  }

  function checkLabel(check) {
    const id = typeof check === 'string' ? check : check.id;
    const labels = {
      'source-loaded': 'Handler loaded successfully',
      'source-unchanged': 'Source stayed unchanged during the run',
      'bounded-local-execution': 'Execution stayed within its allowed boundaries',
      'schedule-executed': 'Every declared delivery was attempted',
      'independent-snapshot': 'Independent receipt snapshot is available',
      'receipt-inputs': 'Receipts match the requested orders',
      'receipt-delivery-links': 'Receipts and delivery records agree',
      'supported-effect': 'Effect is covered by the receiver contract'
    };
    if (id.startsWith('order:')) return 'One correct receipt for ' + id.slice(6);
    if (id.startsWith('delivery:')) return 'Delivery ' + id.slice(9) + ' met its expected outcome';
    if (id.startsWith('execution:')) return 'Execution completed: ' + id.slice(10);
    return labels[id] || id;
  }

  function replay(model, caseId, requestedStep) {
    const plan = model.plans.get(caseId);
    if (!plan) throw new Error('Choose a case in this report.');
    if (!Number.isInteger(requestedStep)) throw new Error('Replay step must be an integer.');
    const total = plan.deliveries.length;
    const step = Math.max(0, Math.min(total, requestedStep));
    const included = new Set(plan.deliveries.slice(0, step).map(delivery => delivery.deliveryId));
    const supported = plan.effectModel === 'receiver-owned-receipt';
    const byCandidate = candidates(model).map(candidate => {
      const view = model.get(caseId, candidate.id);
      const result = view && view.result;
      const events = result && supported ? result.events.filter(event => included.has(event.deliveryId) && EFFECT_EVENTS.has(event.type)) : [];
      const accepted = events.filter(event => event.type === 'receipt-accepted');
      const snapshotAvailable = !!result && result.receipts !== null;
      const snapshot = new Map((snapshotAvailable ? result.receipts : []).map(receipt => [receipt.receiptId, receipt]));
      // The event is a projection of the recording, never a newly observed receipt.
      // A missing independent snapshot is kept separate from these illustrative rows.
      const receipts = accepted.map(event => {
        const observed = snapshot.get(event.receiptId);
        return observed || {
          receiptId: event.receiptId,
          acceptedDeliveryId: event.deliveryId,
          order: event.order || null,
          key: event.key === undefined ? null : event.key,
          fromEventOnly: true
        };
      });
      const observedDeliveries = new Map((result ? result.deliveries : []).map(delivery => [delivery.deliveryId, delivery]));
      const prefixExecuted = plan.deliveries.slice(0, step).every(delivery => {
        const observation = observedDeliveries.get(delivery.deliveryId);
        return observation && observation.attempted && observation.outcome !== 'not-run';
      });
      const unknownOrder = receipts.some(receipt => !receipt.order);
      const available = supported && !!result && prefixExecuted && !unknownOrder;
      const counts = Object.fromEntries(plan.expectedOrders.map(expected => [expected.order.orderId, available ? receipts.filter(receipt => receipt.order.orderId === expected.order.orderId).length : null]));
      let reason = null;
      if (!supported) reason = 'This external effect has no supported receipt replay.';
      else if (!result || !prefixExecuted) reason = 'The selected delivery sequence has incomplete execution evidence.';
      else if (unknownOrder) reason = 'An accepted event lacks the order data needed to display counts.';
      else if (!snapshotAvailable) reason = 'Recorded events only: the independent receipt snapshot is missing.';
      return { id: candidate.id, counts, receipts, events, basis: 'recorded-events', supported, available, snapshotAvailable, reason };
    });
    return { total, step, delivery: step ? plan.deliveries[step - 1] : null, byCandidate, basis: 'recorded-events', complete: step === total };
  }

  root.ProposalData = Object.freeze({ create, candidates, coverage, describe, checkLabel, replay });
})(typeof window !== 'undefined' ? window : globalThis);
