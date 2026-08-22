/* Icons, drawn rather than fetched.
 *
 * No CDN and no build step, so an icon font or a sprite sheet is not on offer.
 * These are 24x24 stroke paths on `currentColor`, which means an icon inherits
 * whatever colour its context has -- a status chip, a disabled button, a
 * callout -- without any of them knowing an icon is involved.
 *
 * Stroke rather than fill throughout: at 16px a filled glyph turns into a blob
 * on a dark background, and every icon here is used at 14-18px.
 */
(function (RF) {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";

  //: path data only; the wrapper supplies the shared attributes
  var PATHS = {
    // navigation and chrome
    film: "M3 4h18v16H3zM7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4",
    plus: "M12 5v14M5 12h14",
    settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" +
              "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H1a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 2.6 7a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H7a1.7 1.7 0 0 0 1-1.5V1a2 2 0 1 1 4 0v.1A1.7 1.7 0 0 0 15 2.6a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V7a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
    sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4" +
         "M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
    moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    monitor: "M3 4h18v12H3zM8 20h8M12 16v4",

    // status
    check: "M20 6L9 17l-5-5",
    x: "M18 6L6 18M6 6l12 12",
    alert: "M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
    info: "M12 16v-4M12 8h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
    clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    pause: "M10 4H6v16h4zM18 4h-4v16h4z",
    play: "M5 3l14 9-14 9V3z",

    // actions
    up: "M12 19V5M5 12l7-7 7 7",
    down: "M12 5v14M19 12l-7 7-7-7",
    trash: "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6",
    upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
    download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
    image: "M3 3h18v18H3zM8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM21 15l-5-5L5 21",
    refresh: "M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15",
    external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3",
    copy: "M9 9h10v12H9zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1",
    search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
    grip: "M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01",
  };

  function icon(name, options) {
    options = options || {};
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", options.weight || "1.75");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("class", "icon" + (options.class ? " " + options.class : ""));
    svg.setAttribute("aria-hidden", "true");
    if (options.size) {
      svg.setAttribute("width", options.size);
      svg.setAttribute("height", options.size);
    }

    var path = document.createElementNS(NS, "path");
    path.setAttribute("d", PATHS[name] || PATHS.info);
    svg.appendChild(path);
    return svg;
  }

  /* The empty-state illustration: a 9:16 frame, because that is what this app
   * makes. Nine of them would be a sprite sheet; one drawn here is enough. */
  function reelArt() {
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 72 108");
    svg.setAttribute("fill", "none");
    svg.setAttribute("class", "art");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML =
      '<rect x="6" y="4" width="60" height="100" rx="8" stroke="currentColor" ' +
      'stroke-width="2" opacity=".45"/>' +
      '<rect x="14" y="16" width="44" height="4" rx="2" fill="currentColor" opacity=".28"/>' +
      '<rect x="14" y="44" width="44" height="26" rx="4" fill="currentColor" opacity=".16"/>' +
      '<rect x="18" y="86" width="36" height="6" rx="3" fill="currentColor" opacity=".28"/>';
    return svg;
  }

  /* The wordmark. A play triangle inside a rounded frame -- the two things this
   * app is about, in one 24px shape. */
  function mark() {
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("class", "mark");
    svg.setAttribute("aria-hidden", "true");
    svg.innerHTML =
      '<rect x="3" y="2" width="18" height="20" rx="5" stroke="currentColor" ' +
      'stroke-width="2"/>' +
      '<path d="M10 8.5l5.5 3.5L10 15.5z" fill="currentColor"/>';
    return svg;
  }

  RF.icons = { icon: icon, reelArt: reelArt, mark: mark, PATHS: PATHS };
  RF.icon = icon;
})(window.RF || (window.RF = {}));
