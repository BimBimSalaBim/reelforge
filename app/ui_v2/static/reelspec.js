/* Frame geometry and crop maths, fetched from GET /api/images/frame.
 *
 * Nothing here is a typed-in constant: the numbers live in app/images.py and
 * inside the emitted storyboard, three of them moved in one afternoon, and a
 * preview that silently stops agreeing with the renderer is worse than none.
 * The maths below mirrors app/images.py -- default_fit, default_crop,
 * Crop.clamped, prepare()'s panel branch, and _panel_y.
 */
(function (RF) {
  "use strict";

  var spec = null;

  function load() {
    if (spec) return Promise.resolve(spec);
    return RF.api.get("/api/images/frame").then(function (payload) {
      spec = payload;
      return spec;
    });
  }

  function get() { return spec; }

  function defaultFit(w, h) {
    return (h && w / h >= spec.upload.wide_ratio) ? "panel" : "full";
  }

  function clampCrop(crop) {
    var w = Math.min(Math.max(crop.w, 0.02), 1);
    var h = Math.min(Math.max(crop.h, 0.02), 1);
    return { x: Math.min(Math.max(crop.x, 0), 1 - w),
             y: Math.min(Math.max(crop.y, 0), 1 - h), w: w, h: h };
  }

  function defaultCrop(w, h, fit) {
    if (!w || !h) return { x: 0, y: 0, w: 1, h: 1 };
    if (fit === "panel") {
      // a wide screenshot is kept whole; a tall one is cropped to the deepest
      // band the frame can draw, centred
      var widest = spec.frame.w / spec.panel.max_h;
      if (w / h >= widest) return { x: 0, y: 0, w: 1, h: 1 };
      var ph = (w / widest) / h;
      return { x: 0, y: Math.max(0, (1 - ph) / 2), w: 1, h: Math.min(ph, 1) };
    }
    var target = spec.frame.w / spec.frame.h;
    var source = w / h;
    if (source > target) {
      var cw = target / source;
      return { x: (1 - cw) / 2, y: 0, w: cw, h: 1 };
    }
    var ch = source / target;
    return { x: 0, y: (1 - ch) / 2, w: 1, h: ch };
  }

  /* What prepare() will produce: scaled to the full frame width, then capped. */
  function panelNaturalHeight(crop, srcW, srcH) {
    return Math.round(spec.frame.w * (crop.h * srcH) / (crop.w * srcW));
  }
  function panelHeight(crop, srcW, srcH) {
    return Math.min(spec.panel.max_h, panelNaturalHeight(crop, srcW, srcH));
  }

  function panelY(height, position) {
    var top = spec.panel.top, bottom = spec.panel.bottom;
    if (position === "top") return top;
    if (position === "centre") return top + Math.max(0, Math.floor((bottom - top - height) / 2));
    return Math.max(top, bottom - height);
  }

  /* Every warning traces to a constant, and each is something the renderer will
   * actually do -- not a guess about taste. */
  function collisions(image, captionsOn) {
    var out = [];
    var crop = image.crop, srcW = image.srcW, srcH = image.srcH;
    if (!srcW || !srcH) return out;

    if (image.fit === "panel") {
      var natural = panelNaturalHeight(crop, srcW, srcH);
      var height = Math.min(natural, spec.panel.max_h);
      if (natural > spec.panel.max_h) {
        out.push({ level: "warn", id: "panel-trimmed",
          message: (natural - spec.panel.max_h) + "px of this crop is trimmed at render — " +
                   "the frame draws at most " + spec.panel.max_h + "px of panel height." });
      }
      var y = panelY(height, image.position || "bottom");
      if (captionsOn && y + height > spec.captions.top) {
        out.push({ level: "warn", id: "caption-overlap",
          message: "The burned-in captions will sit over the bottom " +
                   Math.round(y + height - spec.captions.top) + "px of this screenshot. " +
                   "Move it to centre, or turn captions off." });
      }
    } else {
      var kept = (crop.w * crop.h);
      out.push({ level: "info", id: "full-loss",
        message: "Full bleed keeps a 9:16 slice — " + Math.round((1 - kept) * 100) +
                 "% of this screenshot is discarded." });
      if (captionsOn) {
        out.push({ level: "info", id: "full-scrim",
          message: "The lower third sits under the scrim and the captions." });
      }
    }

    var shownWidth = crop.w * srcW;
    if (shownWidth < spec.frame.w) {
      out.push({ level: "warn", id: "upscaled",
        message: "Zoomed past the source: the crop is " + Math.round(shownWidth) +
                 "px wide and is upscaled ×" + (spec.frame.w / shownWidth).toFixed(1) +
                 " — text in the screenshot will soften." });
    }
    return out;
  }

  function checkFile(file) {
    var name = (file.name || "").toLowerCase();
    var ok = spec.upload.allowed.some(function (ext) { return name.slice(-ext.length) === ext; });
    if (!ok) return "only " + spec.upload.allowed.join(", ") + " are supported";
    if (file.size > spec.upload.max_bytes) {
      // MiB, matching the limit's own definition (12 * 1024 * 1024). Dividing
      // by 1e6 and rounding reported the 12 MB cap as "13 MB".
      var mib = function (n) { return (n / 1048576).toFixed(n < 10485760 ? 1 : 0); };
      return mib(file.size) + " MB is over the " + mib(spec.upload.max_bytes) + " MB limit";
    }
    return null;
  }

  RF.spec = { load: load, get: get, defaultFit: defaultFit, defaultCrop: defaultCrop,
              clampCrop: clampCrop, panelHeight: panelHeight,
              panelNaturalHeight: panelNaturalHeight, panelY: panelY,
              collisions: collisions, checkFile: checkFile };
})(window.RF || (window.RF = {}));
