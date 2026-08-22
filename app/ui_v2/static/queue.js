/* The queue adapter.
 *
 * Everything queue-shaped goes through here so the pages do not care which
 * version of GET /api/queue they are talking to. Today the endpoint returns
 * {running, waiting, done, failed, counts} with no positions -- position is
 * synthesised from the array index and state from which array an entry was in.
 * When the scheduler lands and the payload carries `entries` with real
 * positions, `normalise` becomes a passthrough and no page changes.
 */
(function (RF) {
  "use strict";

  function entry(row, state, position) {
    return {
      jobId: row.id || row.job_id,
      slug: row.slug || "",
      position: position,
      state: state,
      stage: row.stage || row.next_stage || row.failed_stage || null,
      progress: typeof row.progress === "number" ? row.progress : null,
      enqueuedAt: row.queued_at || null,
      startedAt: row.started_at || null,
      etaSeconds: typeof row.eta_seconds === "number" ? row.eta_seconds : null,
      reason: row.reason || null,
      updatedAt: row.updated_at || null,
    };
  }

  function normalise(payload) {
    payload = payload || {};
    if (Array.isArray(payload.entries)) {
      return {
        executor: payload.executor || "inline",
        concurrency: payload.concurrency || 1,
        paused: !!payload.paused,
        entries: payload.entries.map(function (row, i) {
          return entry(row, row.state || "queued",
                       typeof row.position === "number" ? row.position : i);
        }),
        counts: payload.counts || {},
      };
    }

    var entries = [];
    (payload.running || []).forEach(function (row) { entries.push(entry(row, "running", 0)); });
    (payload.waiting || []).forEach(function (row, i) {
      entries.push(entry(row, "queued", entries.length ? i + 1 : i));
    });
    (payload.failed || []).forEach(function (row) { entries.push(entry(row, "failed", -1)); });
    (payload.done || []).forEach(function (row) { entries.push(entry(row, "done", -1)); });

    return {
      executor: payload.executor || "inline",
      concurrency: payload.concurrency || 1,
      paused: !!payload.paused,
      entries: entries,
      counts: payload.counts || {},
    };
  }

  function index(payload) {
    var map = new Map();
    normalise(payload).entries.forEach(function (e) {
      if (e.jobId && !map.has(e.jobId)) map.set(e.jobId, e);
    });
    return map;
  }

  RF.queue = { normalise: normalise, index: index };
})(window.RF || (window.RF = {}));
