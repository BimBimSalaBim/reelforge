/* The jobs board.
 *
 * The design problem here is real and measurable: the store holds 24 jobs, ten
 * of which are called `deer-flow` and seven `ruflo` -- the same repository tried
 * again and again. A list that leads with the slug shows ten identical rows. So
 * every card leads with the name *and* the things that actually tell two runs
 * apart: where it got to, how it ended, and when.
 *
 * The nine-cell stage bar replaces the percentage bar for the same reason. A
 * 66% bar cannot tell you a job is stuck on `align`; nine cells can.
 */
(function (RF) {
  "use strict";

  var el, fmt;
  var STAGE_ORDER = ["ingest", "content", "cover", "visuals", "audio", "align",
                     "storyboard", "render", "verify", "package"];

  var state = { tab: "current", filter: "", jobs: [], queue: null, fingerprint: "" };

  /* ------------------------------------------------------------ the queue */
  /* An estimate is only worth showing if it is honest about being one, so it
   * is rounded to the granularity people actually think in. */
  function eta(seconds) {
    if (seconds === null || seconds === undefined) return "";
    if (seconds < 90) return "under a minute";
    var minutes = seconds / 60;
    if (minutes < 60) return "~" + Math.round(minutes) + " min";
    return "~" + (minutes / 60).toFixed(1) + " h";
  }

  function queueAction(request, label) {
    return request
      .then(function () { return load(); })
      .catch(function (error) {
        RF.dom.toast(label + " failed: " + error.message, { kind: "error", timeout: 9000 });
      });
  }

  function pauseControl(queue) {
    var button = document.querySelector("[data-queue-pause]");
    if (!button) return;
    button.hidden = false;
    button.className = "btn btn--sm " + (queue.paused ? "btn--primary" : "btn--quiet");
    button.onclick = function () {
      queueAction(RF.api.post("/api/queue/" + (queue.paused ? "resume" : "pause"), {}),
                  queue.paused ? "Resume" : "Pause");
    };
  }

  function queueRow(entry, index, count) {
    var running = entry.state === "running";
    return el("div", { class: "queuerow" + (running ? " queuerow--running" : "") },
      el("span", { class: "queuerow__pos" }, running ? "▶" : String(entry.position)),

      el("a", { class: "grow truncate",
                href: "/v2/job.html?id=" + encodeURIComponent(entry.jobId) },
        el("div", { class: "jobcard__name truncate" }, entry.slug || entry.jobId),
        el("div", { class: "jobcard__meta" },
           running
             ? (entry.stage ? "running " + RF.stages.label(entry.stage) : "running")
             : (entry.stage ? "starts at " + RF.stages.label(entry.stage) : "waiting"))),

      entry.etaSeconds ? el("span", { class: "queuerow__eta mono" },
                            running ? eta(entry.etaSeconds) + " left"
                                    : eta(entry.etaSeconds)) : null,

      /* Reordering only applies to jobs that have not started. Moving the
       * running one is refused by the API, so it is not offered here either. */
      running ? null : el("span", { class: "cluster", "data-gap": "2" },
        el("button", { class: "iconbtn", title: "Move up", disabled: index === 0,
          onclick: function () {
            queueAction(RF.api.post("/api/queue/" + entry.jobId + "/move", { delta: -1 }),
                        "Move");
          } }, RF.icon("up", { size: 14 })),
        el("button", { class: "iconbtn", title: "Move down", disabled: index === count - 1,
          onclick: function () {
            queueAction(RF.api.post("/api/queue/" + entry.jobId + "/move", { delta: 1 }),
                        "Move");
          } }, RF.icon("down", { size: 14 }))),

      el("button", { class: "btn btn--sm btn--quiet",
        title: running ? "Stop after the current stage finishes" : "Take it out of the queue",
        onclick: function () { cancel(entry); } },
        running ? "Stop" : "Remove"));
  }

  function cancel(entry) {
    var running = entry.state === "running";
    RF.dom.confirm({
      title: running ? "Stop " + entry.slug + "?" : "Remove " + entry.slug + " from the queue?",
      body: running
        ? "It will finish the stage it is on and then stop. A stage cannot be " +
          "interrupted part-way without leaving a half-written file behind, so " +
          "this is the earliest safe moment."
        : "The reel is kept; it simply stops waiting its turn. You can queue it again.",
      confirmLabel: running ? "Stop after this stage" : "Remove",
      danger: true,
    }).then(function (yes) {
      if (!yes) return;
      queueAction(RF.api.del("/api/queue/" + entry.jobId).then(function (result) {
        if (result && result.note) RF.dom.toast(result.note, { timeout: 8000 });
      }), "Cancel");
    });
  }

  function renderQueue() {
    var section = document.querySelector("[data-queue-section]");
    var body = document.querySelector("[data-queue-body]");
    if (!section || !body) return;

    var queue = RF.queue.normalise(state.queue);
    var live = queue.entries.filter(function (e) {
      return e.state === "running" || e.state === "queued";
    });

    /* The section stays visible while paused even with nothing in it -- a
     * paused queue that looks identical to an empty one is how you end up
     * wondering why nothing starts. */
    if (!live.length && !queue.paused) { section.hidden = true; return; }
    section.hidden = false;
    pauseControl(queue);

    var summary = document.querySelector("[data-queue-summary]");
    if (summary) {
      var running = live.filter(function (e) { return e.state === "running"; }).length;
      var waiting = live.length - running;
      summary.textContent = queue.paused ? "paused"
        : running ? running + " running" + (waiting ? " · " + waiting + " waiting" : "")
        : waiting + " waiting";
    }

    var waitingRows = live.filter(function (e) { return e.state === "queued"; });
    RF.dom.mount(body, el("div", { class: "stack", "data-gap": "2" },
      queue.paused ? el("div", { class: "callout callout--warn" },
        el("div", null,
          el("div", { class: "callout__title" }, "The queue is paused"),
          el("div", null, (state.queue && state.queue.paused_reason) ||
             "Nothing new will start until you resume it."))) : null,

      live.map(function (entry) {
        var index = waitingRows.indexOf(entry);
        return queueRow(entry, index, waitingRows.length);
      }),

      (state.queue && state.queue.gated && state.queue.gated.length)
        ? el("div", { class: "field__hint" },
             "Reels pause for review at " +
             state.queue.gated.map(RF.stages.label).join(" and ") +
             ", so a queued reel will stop there and let the next one start.")
        : null));
  }

  /* ------------------------------------------------------------- job cards */
  /* The list endpoint returns `next_stage`, `failed_stage` and `progress` -- it
   * does NOT return the per-stage array, which only GET /api/jobs/{id} carries.
   * That is enough: everything before `next_stage` is done, `next_stage` is
   * where it stopped, everything after is pending, and `failed_stage` overrides.
   * Reading job.stages here silently produced nine empty cells. */
  function stageStatuses(job, queueEntry) {
    var edge = job.failed_stage || job.next_stage;
    var boundary = edge ? STAGE_ORDER.indexOf(edge) : STAGE_ORDER.length;
    var live = queueEntry && queueEntry.state === "running";
    return STAGE_ORDER.map(function (name, i) {
      if (job.failed_stage && name === job.failed_stage) return "failed";
      if (i < boundary) return "done";
      if (name === job.next_stage) return live ? "running" : "pending";
      return "pending";
    });
  }

  function stageBar(job, queueEntry) {
    var statuses = stageStatuses(job, queueEntry);
    return el("div", { class: "stagebar", "aria-hidden": "true" },
      STAGE_ORDER.map(function (name, i) {
        return el("span", {
          class: "stagebar__cell",
          dataset: { status: statuses[i] },
          title: RF.stages.label(name) + " — " + RF.stages.status(statuses[i]).label,
        });
      }));
  }

  function outcome(job, queueEntry) {
    if (job.failed_stage) {
      return { cls: "chip--failed", text: "failed at " + RF.stages.label(job.failed_stage) };
    }
    if (!job.next_stage) return { cls: "chip--done", text: "finished" };
    if (queueEntry && queueEntry.state === "running") {
      return { cls: "chip--running", text: "running " + RF.stages.label(job.next_stage) };
    }
    return { cls: "", text: "next: " + RF.stages.label(job.next_stage) };
  }

  function jobCard(job, queueEntry) {
    var mark = outcome(job, queueEntry);
    var statuses = stageStatuses(job, queueEntry);
    var done = statuses.filter(function (s) { return s === "done"; }).length;
    return el("a", { class: "jobcard stack", "data-gap": "3",
                     href: "/v2/job.html?id=" + encodeURIComponent(job.id) },
      el("div", { class: "cluster", "data-gap": "2" },
        el("span", { class: "jobcard__name truncate grow" }, job.slug),
        queueEntry && queueEntry.state === "queued"
          ? el("span", { class: "chip chip--queued" }, "#" + queueEntry.position + " queued") : null,
        el("span", { class: "chip " + mark.cls }, mark.text)),
      el("div", { class: "jobcard__meta truncate" },
         (job.url ? job.url.replace(/^https?:\/\//, "") : "") +
         (job.template ? " · " + job.template : "")),
      stageBar(job, queueEntry),
      el("div", { class: "cluster", "data-gap": "2" },
        el("span", { class: "jobcard__meta grow" }, done + " of " + STAGE_ORDER.length + " stages"),
        el("span", { class: "jobcard__meta" }, fmt.relTime(job.updated_at)))
    );
  }

  function renderJobs() {
    var body = document.querySelector("[data-jobs-body]");
    if (!body) return;

    var queueIndex = RF.queue.index(state.queue);
    var needle = state.filter.trim().toLowerCase();
    var rows = state.jobs.filter(function (job) {
      if (!needle) return true;
      var url = job.url || "";
      return (job.slug + " " + url).toLowerCase().indexOf(needle) !== -1;
    });

    if (!rows.length) {
      RF.dom.mount(body, el("div", { class: "empty" },
        el("div", { class: "empty__art" }),
        el("div", { class: "empty__title" },
           state.filter ? "Nothing matches that"
                        : state.tab === "archived" ? "Nothing archived yet" : "No reels yet"),
        el("div", { class: "empty__body" },
           state.filter
             ? "Try a different name or URL."
             : state.tab === "archived"
               ? "Archiving keeps a finished reel and its copy without it crowding this list."
               : "Paste a GitHub repository or a Hugging Face model and ReelForge will write " +
                 "the script, record it, render the video and package the copy that ships with it."),
        state.tab === "current" && !state.filter
          ? el("a", { class: "btn btn--primary", href: "/v2/new.html" }, "Create your first reel")
          : null));
      return;
    }

    RF.dom.mount(body, el("div", { class: "joblist" },
      rows.map(function (job) { return jobCard(job, queueIndex.get(job.id)); })));
  }

  /* ---------------------------------------------------------------- loading */
  function load() {
    var archived = state.tab === "archived";
    return Promise.allSettled([
      RF.api.get("/api/jobs?archived=" + archived),
      RF.api.get("/api/queue"),
      RF.api.get("/api/jobs/counts"),
    ]).then(function (results) {
      if (results[0].status === "fulfilled") state.jobs = results[0].value || [];
      if (results[1].status === "fulfilled") state.queue = results[1].value;
      if (results[2].status === "fulfilled") paintCounts(results[2].value);

      // A fingerprint so polling can back off when nothing is moving, rather
      // than re-rendering the same list every four seconds for ever.
      //
      // It has to cover everything the page draws. It first covered only job
      // `updated_at` and the counts -- and `JobStore.save` does not touch
      // `updated_at`, so reordering the queue changed neither and the board
      // silently kept showing the old order while the API had already moved on.
      var queue = RF.queue.normalise(state.queue);
      var next = state.jobs.map(function (j) { return j.id + j.updated_at; }).join("|") +
                 "|" + queue.entries.map(function (e) {
                   return e.position + e.state + e.jobId;
                 }).join(",") +
                 "|" + queue.paused;
      var changed = next !== state.fingerprint;
      if (changed) {
        renderQueue();
        renderJobs();
        // committed only after the paint: advancing it first meant one render
        // error left the page stale for ever, with every later poll agreeing
        // that nothing had changed
        state.fingerprint = next;
      }
      // While anything is queued or running the poll must stay at full rate:
      // stage handoffs land between polls, and the backoff meant a finished
      // stage could sit on screen for twenty seconds looking current.
      return changed || queue.entries.length > 0;
    });
  }

  function paintCounts(counts) {
    if (!counts) return;
    document.querySelectorAll("[data-tab]").forEach(function (tab) {
      var key = tab.dataset.tab;
      var n = counts[key];
      tab.textContent = (key === "archived" ? "Archived" : "Active") +
                        (typeof n === "number" ? " " + n : "");
    });
  }

  function init() {
    el = RF.dom.el; fmt = RF.dom.fmt;
    RF.stages.refresh();

    var body = document.querySelector("[data-jobs-body]");
    if (body) RF.dom.mount(body, RF.dom.skeleton("card", 4));

    document.querySelectorAll("[data-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        state.tab = tab.dataset.tab;
        state.fingerprint = "";
        document.querySelectorAll("[data-tab]").forEach(function (other) {
          other.setAttribute("aria-selected", String(other === tab));
        });
        load();
      });
    });

    var filter = document.querySelector("[data-filter]");
    if (filter) {
      filter.addEventListener("input", function () {
        state.filter = filter.value;
        renderJobs();
      });
    }

    RF.api.poll(load, 4000, { visibilityAware: true, backoff: true });
  }

  RF.shell.ready(init);
})(window.RF || (window.RF = {}));
