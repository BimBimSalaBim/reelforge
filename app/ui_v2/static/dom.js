/* DOM helpers.
 *
 * `el()` is not a style preference, it is a correctness fix. The v1 UI builds
 * markup by concatenating template strings and calling esc() by hand at about
 * ninety sites; one omission turns a repository name, a stage error or an
 * LLM-authored caption into script injection. Here the default is textContent
 * and escaping stops being something anyone has to remember.
 *
 * Classic script, not an ES module: `node --check` runs on these with no flags,
 * and it is the only JavaScript verification this repo has.
 */
(function (RF) {
  "use strict";

  var BOOLEAN_PROPS = { checked: 1, disabled: 1, selected: 1, hidden: 1, open: 1 };

  function el(tag, props, ...children) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        var value = props[key];
        if (value === null || value === undefined || value === false) return;
        if (key === "class") node.className = value;
        else if (key === "dataset") Object.assign(node.dataset, value);
        else if (key === "style") Object.assign(node.style, value);
        else if (key.slice(0, 2) === "on") node.addEventListener(key.slice(2), value);
        else if (BOOLEAN_PROPS[key]) node[key] = !!value;
        else node.setAttribute(key, value);
      });
    }
    append(node, children);
    return node;
  }

  function append(node, children) {
    children.forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      if (Array.isArray(child)) return append(node, child);
      node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
    });
  }

  function frag() {
    var f = document.createDocumentFragment();
    append(f, Array.prototype.slice.call(arguments));
    return f;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function mount(node, children) {
    clear(node);
    append(node, Array.isArray(children) ? children : [children]);
    return node;
  }

  /* ------------------------------------------------------------ formatting */
  var MINUTE = 60, HOUR = 3600, DAY = 86400;

  function relTime(iso) {
    if (!iso) return "";
    // Stage timestamps carry a `Z` suffix. Date handles it; Python's
    // fromisoformat does not, which is a real bug elsewhere in this project.
    var then = new Date(iso).getTime();
    if (!then) return "";
    var secs = Math.max(0, (Date.now() - then) / 1000);
    if (secs < 45) return "just now";
    if (secs < HOUR) return Math.round(secs / MINUTE) + "m ago";
    if (secs < DAY) return Math.round(secs / HOUR) + "h ago";
    if (secs < DAY * 7) return Math.round(secs / DAY) + "d ago";
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "";
    if (seconds < 1) return seconds.toFixed(2) + "s";
    if (seconds < MINUTE) return Math.round(seconds) + "s";
    var mins = Math.floor(seconds / MINUTE);
    var rest = Math.round(seconds % MINUTE);
    if (mins < 60) return mins + "m" + (rest ? " " + rest + "s" : "");
    return Math.floor(mins / 60) + "h " + (mins % 60) + "m";
  }

  function bytes(n) {
    if (!n) return "0 B";
    var units = ["B", "KB", "MB", "GB"], i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
    return (i === 0 ? n : n.toFixed(1)) + " " + units[i];
  }

  /* ---------------------------------------------------------------- toasts */
  function toast(message, options) {
    options = options || {};
    var host = document.querySelector("[data-toaster]");
    if (!host) return null;
    var node = el("div", { class: "toast" + (options.kind ? " toast--" + options.kind : "") },
                  message);
    host.appendChild(node);
    var life = options.timeout === undefined ? 5000 : options.timeout;
    if (life) setTimeout(function () { node.remove(); }, life);
    return node;
  }

  /* -------------------------------------------------------------- dialogue */
  function dialog(content, options) {
    options = options || {};
    var box = el("dialog", { class: "dialogwrap", "aria-label": options.label || "Dialog" },
                 el("div", { class: "dialog" }, content));
    document.body.appendChild(box);
    box.addEventListener("close", function () { box.remove(); });
    box.showModal();
    return { close: function (value) { box.close(value || ""); }, node: box };
  }

  /* A real dialog rather than window.confirm, so a destructive action can
   * explain itself and, when it matters, demand the name be typed. */
  function confirmDialog(options) {
    options = options || {};
    return new Promise(function (resolve) {
      var input = options.requireText
        ? el("input", { class: "input", placeholder: options.requireText,
                        "aria-label": "Type " + options.requireText + " to confirm" })
        : null;
      var ok = el("button", {
        class: "btn " + (options.danger ? "btn--danger" : "btn--primary"),
        disabled: !!options.requireText,
        onclick: function () { handle.close(); resolve(true); },
      }, options.confirmLabel || "Confirm");

      if (input) {
        input.addEventListener("input", function () {
          ok.disabled = input.value.trim() !== options.requireText;
        });
      }

      var handle = dialog(frag(
        el("div", { class: "dialog__head" },
          el("h2", { class: "card__title" }, options.title || "Are you sure?")),
        el("div", { class: "dialog__body stack", "data-gap": "3" },
          el("p", { class: "muted" }, options.body || ""),
          input),
        el("div", { class: "dialog__foot" },
          el("button", { class: "btn btn--ghost",
                         onclick: function () { handle.close(); resolve(false); } }, "Cancel"),
          ok)
      ), { label: options.title });

      handle.node.addEventListener("close", function () { resolve(false); });
      if (input) input.focus(); else ok.focus();
    });
  }

  function skeleton(kind, count) {
    var out = document.createDocumentFragment();
    for (var i = 0; i < (count || 3); i += 1) {
      out.appendChild(el("div", { class: "skeleton skeleton--" + (kind || "card") }));
    }
    return out;
  }

  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; },
                                                      function () { return false; });
    }
    return Promise.resolve(false);
  }

  /* Callouts are the app's warning surface, and an icon is what makes one
   * scannable in a column of cards -- colour alone is not enough for anyone
   * who cannot distinguish amber from red. */
  var CALLOUT_ICON = { info: "info", warn: "alert", error: "x", ok: "check" };

  function callout(kind, title, body, extra) {
    return el("div", { class: "callout callout--" + kind },
      RF.icon ? RF.icon(CALLOUT_ICON[kind] || "info", { size: 17, class: "callout__icon" }) : null,
      el("div", { class: "grow" },
        title ? el("div", { class: "callout__title" }, title) : null,
        body ? el("div", null, body) : null,
        extra));
  }

  RF.dom = {
    el: el, frag: frag, clear: clear, mount: mount, callout: callout,
    fmt: { relTime: relTime, duration: duration, bytes: bytes },
    toast: toast, dialog: dialog, confirm: confirmDialog,
    skeleton: skeleton, copy: copy,
  };
})(window.RF || (window.RF = {}));
