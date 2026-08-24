/* Stage and status metadata.
 *
 * The order is always taken from the job payload -- `JobView.of` guarantees
 * `stages` is in STAGE_ORDER -- and never hardcoded here, so adding a stage to
 * the pipeline does not need a UI change. The blurbs are seeded from the copy
 * in app/api/routes_system.py and refreshed at runtime from GET /api/stages,
 * which the v1 UI never calls even though it exists.
 */
(function (RF) {
  "use strict";

  var LABELS = {
    ingest: "Ingest", content: "Content", cover: "Cover", visuals: "Visuals", audio: "Audio",
    align: "Align", storyboard: "Storyboard", render: "Render",
    verify: "Verify", package: "Package",
  };

  var BLURBS = {
    ingest: "Fetch the facts from GitHub or Hugging Face",
    content: "Write the script, fact sheet, cover spec and platform copy",
    cover: "Render the cover image",
    visuals: "Generate stills, clips and a cover backdrop with ComfyUI, when switched on",
    audio: "Synthesize or accept the narration",
    align: "Align the narration to the phrase list",
    storyboard: "Write the storyboard and prove it renders",
    render: "Render and encode the video",
    verify: "Check the encoded file against platform requirements",
    package: "Collect everything into a bundle",
  };

  var STATUS = {
    pending:  { label: "Not run",   cls: "" },
    running:  { label: "Running",   cls: "chip--running" },
    review:   { label: "Review",    cls: "chip--review" },
    done:     { label: "Done",      cls: "chip--done", terminal: true },
    failed:   { label: "Failed",    cls: "chip--failed", terminal: true },
    skipped:  { label: "Skipped",   cls: "chip--skipped", terminal: true },
  };

  function label(stage) { return LABELS[stage] || stage; }
  function blurb(stage) { return BLURBS[stage] || ""; }
  function status(name) { return STATUS[name] || STATUS.pending; }

  function refresh() {
    return RF.api.get("/api/stages").then(function (rows) {
      (rows || []).forEach(function (row) {
        if (row && row.stage && row.description) BLURBS[row.stage] = row.description;
      });
      return BLURBS;
    }).catch(function () { return BLURBS; });
  }

  RF.stages = { LABELS: LABELS, BLURBS: BLURBS, STATUS: STATUS,
                label: label, blurb: blurb, status: status, refresh: refresh };
})(window.RF || (window.RF = {}));
