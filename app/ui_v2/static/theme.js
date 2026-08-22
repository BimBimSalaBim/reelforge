/* Theme resolution, before first paint.
 *
 * Loaded synchronously in each page's <head> -- deliberately not deferred. A
 * deferred script runs after the first paint, so a light-preferring viewer sees
 * a black flash on every navigation, which in a multi-page app is every click.
 *
 * The stored value is "light", "dark" or "system". System is resolved here into
 * an explicit attribute so the stylesheet needs one theme block rather than the
 * same palette written twice.
 */
(function () {
  "use strict";

  var KEY = "reelforge-theme";

  function stored() {
    try { return localStorage.getItem(KEY) || "system"; } catch (e) { return "system"; }
  }

  function resolve(choice) {
    if (choice === "light" || choice === "dark") return choice;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light" : "dark";
  }

  function apply(choice) {
    document.documentElement.setAttribute("data-theme", resolve(choice));
    document.documentElement.dataset.themeChoice = choice;
  }

  apply(stored());

  // Follow the system while the choice is "system", so a viewer who switches
  // their OS at dusk does not have to reload.
  if (window.matchMedia) {
    var query = window.matchMedia("(prefers-color-scheme: light)");
    var onChange = function () { if (stored() === "system") apply("system"); };
    if (query.addEventListener) query.addEventListener("change", onChange);
    else if (query.addListener) query.addListener(onChange);
  }

  window.RFTheme = {
    get: stored,
    set: function (choice) {
      try { localStorage.setItem(KEY, choice); } catch (e) { /* private mode */ }
      apply(choice);
    },
    resolved: function () { return resolve(stored()); },
    cycle: function () {
      var order = ["system", "light", "dark"];
      var next = order[(order.indexOf(stored()) + 1) % order.length];
      window.RFTheme.set(next);
      return next;
    },
  };
})();
