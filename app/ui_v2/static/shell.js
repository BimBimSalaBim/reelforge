/* The shared header, and page boot.
 *
 * Every page calls RF.shell.ready(init). The header is built here rather than
 * repeated in five documents, which is the one thing a multi-page app has to
 * get right or it becomes five apps.
 */
(function (RF) {
  "use strict";

  var el = null;   // resolved at ready(), after dom.js has run

  /* Sections only. "New reel" is the primary action and lives as the button on
   * the right -- having it in both places put two of it in the header. */
  var NAV = [
    { href: "/v2/", label: "Reels", page: "jobs" },
    { href: "/v2/settings.html", label: "Settings", page: "settings" },
  ];

  function build(page) {
    var host = document.querySelector("[data-shell]");
    if (!host) return;

    var ICONS = { jobs: "film", settings: "settings" };
    var nav = el("nav", { class: "shell__nav" }, NAV.map(function (item) {
      return el("a", {
        class: "shell__link", href: item.href,
        "aria-current": item.page === page ? "page" : null,
      }, RF.icon(ICONS[item.page] || "info", { size: 15 }), item.label);
    }));

    RF.dom.mount(host, [
      el("a", { class: "shell__mark", href: "/v2/" },
        RF.icons.mark(), "ReelForge"),
      nav,
      el("span", { class: "grow" }),
      el("span", { class: "badge", "data-executor": "", title: "Executor" }, "…"),
      themeButton(),
      el("a", { class: "shell__link shell__link--quiet", href: "/",
                title: "The previous interface" }, "Classic"),
      el("a", { class: "btn btn--primary btn--sm", href: "/v2/new.html",
                "aria-current": page === "new" ? "page" : null },
         RF.icon("plus", { size: 15 }), "New reel"),
    ]);

    RF.api.get("/api/health").then(function (health) {
      var pill = host.querySelector("[data-executor]");
      if (pill) pill.textContent = health.executor || "inline";
    }).catch(function () {
      var pill = host.querySelector("[data-executor]");
      if (pill) { pill.textContent = "offline"; pill.classList.add("chip--failed"); }
    });
  }

  /* Three states, not two: "system" is a real choice and the one most people
   * want, so it is in the cycle rather than being the absence of a choice. */
  var THEME_LABEL = { system: "Match the system", light: "Light", dark: "Dark" };
  var THEME_ICON = { system: "monitor", light: "sun", dark: "moon" };

  function themeButton() {
    var choice = window.RFTheme ? window.RFTheme.get() : "dark";
    var button = el("button", {
      class: "iconbtn", type: "button",
      title: THEME_LABEL[choice], "aria-label": "Theme: " + THEME_LABEL[choice],
    }, RF.icon(THEME_ICON[choice], { size: 17 }));

    button.addEventListener("click", function () {
      var next = window.RFTheme.cycle();
      RF.dom.mount(button, RF.icon(THEME_ICON[next], { size: 17 }));
      button.title = THEME_LABEL[next];
      button.setAttribute("aria-label", "Theme: " + THEME_LABEL[next]);
      RF.dom.toast(THEME_LABEL[next], { timeout: 1600 });
    });
    return button;
  }

  function ready(init) {
    function boot() {
      el = RF.dom.el;
      build(document.documentElement.dataset.page || "");
      try {
        init();
      } catch (error) {
        // A page script that throws during boot leaves a blank column and
        // nothing but a console line. Say so on the page instead.
        var main = document.querySelector("#main .page__body") || document.body;
        main.appendChild(RF.dom.el("div", { class: "callout callout--error" },
          RF.dom.el("div", null,
            RF.dom.el("div", { class: "callout__title" }, "This page failed to start"),
            RF.dom.el("div", null, String(error && error.message || error)))));
        throw error;
      }
    }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }

  RF.shell = { ready: ready, NAV: NAV };
})(window.RF || (window.RF = {}));
