/* The reel-frame preview, which is also the cropper.
 *
 * There is no separate crop box that the user then has to imagine inside a
 * reel. They drag the screenshot around inside an actual 9:16 frame, with the
 * eyebrow pill, the caption band and the safe area drawn where the renderer
 * puts them.
 *
 * The trick that makes it trustworthy: the stage is literally 1080x1920 CSS
 * pixels, scaled by a transform. So `top: 380px` inside it *is* y=380 in the
 * rendered frame, and the eyebrow's font-size is literally 31px. The CSS
 * numbers are the Python numbers, which is what keeps them from drifting.
 */
(function (RF) {
  "use strict";

  function create(host, options) {
    options = options || {};
    var el = RF.dom.el;
    var spec = RF.spec.get();
    var W = spec.frame.w, H = spec.frame.h;

    var img = el("img", { class: "rf-img", draggable: "false", alt: "" });
    var media = el("div", { class: "rf-media" }, img);
    var eyebrow = el("div", { class: "rf-eyebrow" }, el("i"), el("span"));
    var trim = el("div", { class: "rf-trim", hidden: true });
    var stage = el("div", { class: "rf-stage" },
      el("div", { class: "rf-ground" }),
      media,
      trim,
      el("div", { class: "rf-scrim", hidden: true }),
      el("div", { class: "rf-chrome" }),
      eyebrow,
      el("div", { class: "rf-band", hidden: true }, "burned-in captions"),
      el("div", { class: "rf-safe" }));
    var frame = el("div", { class: "reelframe" }, stage);
    RF.dom.mount(host, frame);

    var model = { fit: "panel", position: "bottom", crop: { x: 0, y: 0, w: 1, h: 1 },
                  srcW: 0, srcH: 0, url: null, eyebrow: "", captions: true };

    /* One observer keeps the 1080-wide stage fitted to whatever box it is in. */
    var observer = new ResizeObserver(function (entries) {
      var width = entries[0].contentRect.width;
      stage.style.transform = "scale(" + (width / W) + ")";
    });
    observer.observe(frame);

    function paint() {
      var crop = model.crop;
      var full = model.fit === "full";
      var boxW = W;
      var boxH = full ? H : RF.spec.panelHeight(crop, model.srcW, model.srcH);
      var natural = full ? H : RF.spec.panelNaturalHeight(crop, model.srcW, model.srcH);
      var top = full ? 0 : RF.spec.panelY(boxH, model.position);

      media.dataset.fit = model.fit;
      media.style.width = boxW + "px";
      media.style.height = boxH + "px";
      media.style.top = top + "px";
      media.style.left = "0px";

      // the image inside, positioned so `crop` exactly fills the box
      img.style.width = (boxW / crop.w) + "px";
      img.style.left = (-crop.x * boxW / crop.w) + "px";
      img.style.height = (natural / crop.h) + "px";
      img.style.top = (-crop.y * natural / crop.h) + "px";

      // what prepare() will centre-crop away, drawn rather than discovered later
      var over = natural - boxH;
      trim.hidden = over <= 1 || full;
      if (!trim.hidden) {
        trim.style.top = top + "px";
        trim.style.height = boxH + "px";
        trim.dataset.amount = Math.round(over) + "px trimmed";
      }

      stage.querySelector(".rf-scrim").hidden = !full;
      eyebrow.lastChild.textContent = model.eyebrow || "";
      eyebrow.hidden = !model.eyebrow;
      stage.querySelector(".rf-band").hidden = !model.captions;
      if (model.url && img.getAttribute("src") !== model.url) img.setAttribute("src", model.url);

      if (options.onChange) options.onChange(model);
    }

    function setSource(source) {
      model.url = source.url; model.srcW = source.srcW; model.srcH = source.srcH;
      paint();
    }
    function setImage(next) {
      Object.assign(model, next);
      if (next.crop) model.crop = RF.spec.clampCrop(next.crop);
      paint();
    }
    function setPalette(palette) {
      if (!palette) return;
      var ground = stage.querySelector(".rf-ground");
      ground.style.setProperty("--bg", (palette.bg || [10, 11, 18]).join(" "));
      ground.style.setProperty("--glow", (palette.accent || [124, 124, 248]).join(" "));
      ground.style.setProperty("--support", (palette.support || [64, 224, 208]).join(" "));
    }

    /* ------------------------------------------------------------- cropper */
    function attachCropper(handlers) {
      handlers = handlers || {};
      var dragging = null;

      function viewport() {
        var box = media.getBoundingClientRect();
        return { w: box.width, h: box.height };
      }
      function clamp(v, hi) { return Math.min(Math.max(v, 0), hi); }

      media.addEventListener("pointerdown", function (event) {
        dragging = { px: event.clientX, py: event.clientY,
                     sx: model.crop.x, sy: model.crop.y };
        media.setPointerCapture(event.pointerId);
        media.classList.add("is-dragging");
      });
      media.addEventListener("pointermove", function (event) {
        if (!dragging) return;
        var view = viewport();
        // dragging right moves the visible window left, hence the sign
        var dx = (event.clientX - dragging.px) / view.w * model.crop.w;
        var dy = (event.clientY - dragging.py) / view.h * model.crop.h;
        model.crop.x = clamp(dragging.sx - dx, 1 - model.crop.w);
        model.crop.y = clamp(dragging.sy - dy, 1 - model.crop.h);
        paint();
      });
      function release() {
        if (!dragging) return;
        dragging = null;
        media.classList.remove("is-dragging");
        if (handlers.onCommit) handlers.onCommit(model);
      }
      media.addEventListener("pointerup", release);
      media.addEventListener("pointercancel", release);

      /* Zoom anchored at the cursor, not the centre: centre-anchored zoom
       * fights the user, which is how the first cropper behaved. */
      media.addEventListener("wheel", function (event) {
        event.preventDefault();
        var box = media.getBoundingClientRect();
        var fx = (event.clientX - box.left) / box.width;
        var fy = (event.clientY - box.top) / box.height;
        var factor = Math.exp(event.deltaY * 0.0015);
        var nw = Math.min(Math.max(model.crop.w * factor, 0.05), 1);
        var nh = Math.min(Math.max(model.crop.h * factor, 0.05), 1);
        if (model.fit === "full") {
          // a full-bleed crop must stay 9:16 in source pixels
          nh = Math.min(1, (nw * model.srcW) * (H / W) / model.srcH);
        }
        model.crop.x = clamp(model.crop.x + (model.crop.w - nw) * fx, 1 - nw);
        model.crop.y = clamp(model.crop.y + (model.crop.h - nh) * fy, 1 - nh);
        model.crop.w = nw; model.crop.h = nh;
        paint();
        clearTimeout(media._commit);
        media._commit = setTimeout(function () {
          if (handlers.onCommit) handlers.onCommit(model);
        }, 300);
      }, { passive: false });

      return { detach: function () { observer.disconnect(); } };
    }

    paint();
    return { setSource: setSource, setImage: setImage, setPalette: setPalette,
             attachCropper: attachCropper, model: model,
             destroy: function () { observer.disconnect(); } };
  }

  RF.frame = { create: create };
})(window.RF || (window.RF = {}));
