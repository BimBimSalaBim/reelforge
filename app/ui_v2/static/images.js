/* Screenshots on a reel that already exists.
 *
 * The same frame component the new-reel form uses, pointed at uploaded files
 * rather than staged ones -- which is the whole reason `frame.js` knows nothing
 * about jobs or staging. Changes PATCH immediately and re-cut the bitmap the
 * renderer pastes, so what you see here is the file that gets drawn.
 */
(function (RF) {
  "use strict";

  var el;
  var state = { id: null, job: null, selected: null, roles: [], frame: null };

  function q(name) { return new URLSearchParams(location.search).get(name); }

  function sourceUrl(image) {
    return "/api/jobs/" + encodeURIComponent(state.id) +
           "/artifacts/uploads/images/" + encodeURIComponent(image.filename);
  }

  function eyebrowFor(role) {
    var spec = RF.spec.get();
    return (spec.roles && spec.roles[role]) || "A LOOK";
  }

  function renderHead() {
    RF.dom.mount(document.querySelector("[data-head]"), [
      el("div", { class: "cluster", "data-gap": "3" },
        el("h1", { class: "section__title" }, "Screenshots"),
        el("span", { class: "badge" }, state.job.slug),
        el("span", { class: "grow" }),
        el("label", { class: "btn btn--sm" }, RF.icon("upload", { size: 14 }), "Add",
          el("input", { type: "file", multiple: "multiple", hidden: true,
            accept: "image/png,image/jpeg,image/webp",
            onchange: function (event) { add(event.target.files); } })),
        el("a", { class: "btn btn--sm btn--ghost",
                  href: "/v2/job.html?id=" + encodeURIComponent(state.id) },
           "Back to the reel")),
      el("div", { class: "jobcard__meta" },
         "Changing any of these rewrites the storyboard, so the reel is " +
         "rendered again from the render stage on."),
    ]);
  }

  function renderList() {
    var host = document.querySelector("[data-list]");
    var images = state.job.images || [];

    if (!images.length) {
      return RF.dom.mount(host, el("div", { class: "empty" },
        el("div", { class: "empty__art" }, RF.icons.reelArt()),
        el("div", { class: "empty__title" }, "No screenshots"),
        el("div", { class: "empty__body" },
           "The reel renders exactly as it would have without them — the layout " +
           "that needs one is simply never chosen.")));
    }

    RF.dom.mount(host, images.map(function (image) {
      var on = image.id === state.selected;
      return el("div", { class: "card stack", "data-gap": "3",
                         dataset: on ? { selected: "1" } : {} },
        el("div", { class: "cluster", "data-gap": "2" },
          el("button", { class: "btn btn--sm" + (on ? " btn--primary" : " btn--quiet"),
            onclick: function () { state.selected = image.id; render(); } },
             on ? "Editing" : "Edit"),
          el("span", { class: "jobcard__name truncate grow" }, image.filename),
          el("button", { class: "btn btn--sm btn--danger",
            onclick: function () { remove(image); } },
             RF.icon("trash", { size: 14 }), "Remove")),

        el("div", { class: "cluster", "data-gap": "2" },
          el("select", { class: "select",
            onchange: function (e) { save(image, { role: e.target.value }); } },
            state.roles.map(function (role) {
              return el("option", { value: role.key, selected: image.role === role.key },
                        role.label);
            })),
          el("div", { class: "segmented" },
            [["panel", "Panel"], ["full", "Full bleed"]].map(function (pair) {
              return el("button", { type: "button", class: "segmented__item",
                "aria-pressed": String(image.fit === pair[0]),
                onclick: function () { save(image, { fit: pair[0] }); } }, pair[1]);
            })),
          el("div", { class: "segmented" },
            ["top", "centre", "bottom"].map(function (pos) {
              return el("button", { type: "button", class: "segmented__item",
                disabled: image.fit === "full",
                title: image.fit === "full"
                  ? "A full-bleed image fills the frame, so it has nowhere to move"
                  : null,
                "aria-pressed": String((image.position || "bottom") === pos),
                onclick: function () { save(image, { position: pos }); } }, pos);
            }))),

        el("input", { class: "input", placeholder: "Caption (optional)",
          value: image.caption || "",
          onchange: function (e) { save(image, { caption: e.target.value.slice(0, 44) }); } }),

        el("div", { class: "jobcard__meta mono" },
           image.source_width + "×" + image.source_height + " source · drawn at " +
           image.prepared_width + "×" + image.prepared_height));
    }));
  }

  function renderPreview() {
    var host = document.querySelector("[data-preview]");
    var images = state.job.images || [];
    var current = images.filter(function (i) { return i.id === state.selected; })[0];
    if (!current) return RF.dom.clear(host);

    var frameHost = el("div");
    var warnings = el("div", { class: "stack", "data-gap": "2" });
    RF.dom.mount(host, el("div", { class: "card stack", "data-gap": "3" },
      el("div", { class: "card__title" }, "In the reel"),
      frameHost,
      el("div", { class: "field__hint" }, "Drag to move, scroll to zoom."),
      warnings));

    var frame = RF.frame.create(frameHost, {
      onChange: function (model) {
        RF.dom.mount(warnings, RF.spec.collisions({
          fit: model.fit, position: model.position, crop: model.crop,
          srcW: current.source_width, srcH: current.source_height,
        }, state.job.captions !== false).map(function (w) {
          return el("div", { class: "callout callout--" + (w.level === "warn" ? "warn" : "info") },
                    el("div", null, w.message));
        }));
      },
    });
    frame.setSource({ url: sourceUrl(current), srcW: current.source_width,
                      srcH: current.source_height });
    frame.setImage({
      fit: current.fit, position: current.position || "bottom",
      crop: { x: current.crop_x, y: current.crop_y, w: current.crop_w, h: current.crop_h },
      eyebrow: eyebrowFor(current.role), captions: state.job.captions !== false,
    });
    frame.attachCropper({
      onCommit: function (model) {
        save(current, { crop_x: model.crop.x, crop_y: model.crop.y,
                        crop_w: model.crop.w, crop_h: model.crop.h }, true);
      },
    });
    state.frame = frame;
  }

  function save(image, patch, quiet) {
    return RF.api.patch("/api/jobs/" + encodeURIComponent(state.id) +
                        "/images/" + image.id, patch)
      .then(function () { if (!quiet) return reload(); })
      .catch(function (error) {
        RF.dom.toast(error.message, { kind: "error", timeout: 9000 });
      });
  }

  function add(files) {
    var form = new FormData();
    for (var i = 0; i < files.length; i += 1) form.append("files", files[i]);
    RF.api.upload("/api/jobs/" + encodeURIComponent(state.id) + "/images?role=other", form)
      .then(function (result) {
        (result.problems || []).forEach(function (problem) {
          RF.dom.toast(problem, { kind: "error", timeout: 9000 });
        });
        if ((result.added || []).length) state.selected = result.added[0].id;
        return reload();
      })
      .catch(function (error) {
        RF.dom.toast(error.message, { kind: "error", timeout: 9000 });
      });
  }

  function remove(image) {
    RF.dom.confirm({
      title: "Remove " + image.filename + "?",
      body: "The storyboard is written again without it, so the reel is rendered " +
            "from the render stage on.",
      confirmLabel: "Remove", danger: true,
    }).then(function (yes) {
      if (!yes) return;
      RF.api.del("/api/jobs/" + encodeURIComponent(state.id) + "/images/" + image.id)
        .then(function () { state.selected = null; return reload(); })
        .catch(function (error) { RF.dom.toast(error.message, { kind: "error" }); });
    });
  }

  function render() { renderHead(); renderList(); renderPreview(); }

  function reload() {
    return RF.api.get("/api/jobs/" + encodeURIComponent(state.id)).then(function (job) {
      state.job = job;
      var images = job.images || [];
      if (!images.some(function (i) { return i.id === state.selected; })) {
        state.selected = images.length ? images[0].id : null;
      }
      render();
    });
  }

  function init() {
    el = RF.dom.el;
    state.id = q("id");
    if (!state.id) {
      return RF.dom.mount(document.querySelector("[data-list]"),
        el("div", { class: "empty" },
          el("div", { class: "empty__title" }, "No reel selected"),
          el("a", { class: "btn btn--primary", href: "/v2/" }, "Back to reels")));
    }
    Promise.all([RF.api.get("/api/jobs/images/roles"), RF.spec.load()])
      .then(function (results) {
        state.roles = (results[0] || {}).roles || [];
        return reload();
      })
      .catch(function (error) {
        RF.dom.mount(document.querySelector("[data-list]"),
          el("div", { class: "callout callout--error" },
            el("div", null,
              el("div", { class: "callout__title" }, "Could not load this reel"),
              el("div", null, error.message))));
      });
  }

  RF.shell.ready(init);
})(window.RF || (window.RF = {}));
