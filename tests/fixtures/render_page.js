/* Render one v2 page's script against real API payloads, under a DOM stub.
 *
 * `node --check` proves a file parses; it cannot prove the page works. This
 * catches the class that actually shipped: reading a field the API does not
 * return, or calling .map on an object. Both look fine until the page is open.
 *
 * Usage: node render_page.js <script.js> <fixtures-dir>
 */
const fs = require("fs");
const path = require("path");

/* `el()` decides whether to nest a child or stringify it with
 * `child instanceof Node`. Plain objects fail that check, so an earlier version
 * of this stub quietly turned every element into the text "[object Object]"
 * and reported a page full of them as rendering fine. The stub has to satisfy
 * the same check the real DOM does. */
function DOMNode() {}
global.Node = DOMNode;

function node(tag) {
  const n = {
    tagName: tag, children: [], attrs: {}, dataset: {}, style: {}, _text: "", _html: "",
    classList: { add() {}, remove() {}, contains() { return false; } },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); },
    insertBefore(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener() {}, removeEventListener() {}, remove() {}, focus() {},
    showModal() {}, close() {}, scrollIntoView() {},
    getBoundingClientRect() { return { width: 300, height: 500, left: 0, top: 0 }; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    get firstChild() { return this.children[0]; },
    set textContent(v) { this._text = v; this.children = []; },
    get textContent() { return this._text; },
    set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; },
    set className(v) { this.attrs.class = v; }, get className() { return this.attrs.class || ""; },
    set value(v) { this._v = v; }, get value() { return this._v === undefined ? "" : this._v; },
    set checked(v) { this._c = v; }, get checked() { return !!this._c; },
    set disabled(v) { this.attrs.disabled = v; }, get disabled() { return !!this.attrs.disabled; },
    set hidden(v) { this.attrs.hidden = v; }, get hidden() { return !!this.attrs.hidden; },
  };
  Object.setPrototypeOf(n, DOMNode.prototype);
  return n;
}

const hosts = {};
const root = node("html");
root.dataset.page = "settings";

global.window = {
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {},
  location: { search: "?id=demo", hash: "", pathname: "/v2/settings.html" },
};
global.localStorage = { _v: {}, getItem(k) { return this._v[k] || null; },
                        setItem(k, v) { this._v[k] = v; } };
global.history = { replaceState() {} };
global.location = global.window.location;
global.URLSearchParams = URLSearchParams;
global.navigator = {};
global.ResizeObserver = function () { return { observe() {}, disconnect() {} }; };
global.EventSource = function () { return { addEventListener() {}, close() {} }; };
global.AbortController = function () { return { signal: {}, abort() {} }; };
global.FormData = function () { this.append = () => {}; };
global.XMLHttpRequest = function () { this.open = () => {}; this.send = () => {}; };
global.document = {
  readyState: "complete", hidden: false, documentElement: root, body: node("body"),
  createElement: node, createElementNS: (ns, t) => node(t),
  createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
  createDocumentFragment: () => node("#fragment"),
  addEventListener() {},
  querySelector(sel) { return hosts[sel] || (hosts[sel] = node("div")); },
  // RF.dom.mount clears and re-appends; keep every host reachable from one place
  querySelectorAll() { return []; },
};

// Route fetches to fixture files by path, so the page sees the real shapes.
const dir = process.argv[3];
const ROUTES = {
  "/api/settings/secrets": "secrets.json",
  "/api/settings": "settings.json",
  "/api/config/profiles": "profiles.json",
  "/api/stages": null,
  "/api/health": null,
  "/api/queue": null,
};
// Job routes are matched by prefix, and the artifact ones 404 on purpose: a
// stage that is still running has not written its output yet, which is the
// state that made a working pipeline look broken.
const JOB_PREFIX = "/api/jobs/";
const NOT_FOUND = ["/storyboard", "/content", "/alignment"];
global.fetch = (url) => {
  const clean = url.split("?")[0];
  if (clean.startsWith(JOB_PREFIX)) {
    if (NOT_FOUND.some((suffix) => clean.endsWith(suffix))) {
      return Promise.resolve({
        ok: false, status: 404,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve({ detail: "no storyboard yet" }),
        text: () => Promise.resolve('{"detail":"no storyboard yet"}'),
      });
    }
    const body = JSON.parse(fs.readFileSync(path.join(dir, "job.json"), "utf8"));
    return Promise.resolve({
      ok: true, status: 200, headers: { get: () => "application/json" },
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
    });
  }
  const match = Object.keys(ROUTES).find((p) => clean === p);
  if (match === undefined) return Promise.reject(new Error("unrouted fetch: " + url));
  const file = ROUTES[match];
  const body = file ? JSON.parse(fs.readFileSync(path.join(dir, file), "utf8")) : {};
  return Promise.resolve({
    ok: true, status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
};

const base = path.join(__dirname, "..", "..", "app", "ui_v2", "static");
for (const f of ["dom.js", "icons.js", "api.js", "stages.js", "queue.js", "shell.js"]) {
  eval(fs.readFileSync(path.join(base, f), "utf8"));
}

let failed = null;
process.on("unhandledRejection", (err) => { failed = err; });
eval(fs.readFileSync(process.argv[2], "utf8"));

/* A page that catches its own error and renders "could not be loaded" is
 * exactly what the user sees, and it is not an unhandled rejection -- so
 * looking only for a thrown error finds nothing. Walk what was actually
 * mounted and fail on an error callout, which is the same signal a person
 * gets from the screen. */
function walk(n, out) {
  if (!n || typeof n !== "object") return out;
  if (typeof n.className === "string" && n.className.indexOf("callout--error") !== -1) {
    out.push(text(n));
  }
  (n.children || []).forEach((c) => walk(c, out));
  return out;
}
function text(n) {
  if (!n || typeof n !== "object") return String(n === undefined ? "" : n);
  if (n.nodeType === 3) return n.textContent;
  return (n._text || "") + (n.children || []).map(text).join(" ");
}

setTimeout(() => {
  if (failed) {
    console.error("RENDER FAILED: " + (failed && failed.message || failed));
    process.exit(1);
  }
  const errors = [];
  Object.keys(hosts).forEach((k) => walk(hosts[k], errors));
  walk(document.body, errors);
  if (errors.length) {
    console.error("PAGE RENDERED AN ERROR: " + errors.join(" | ").trim());
    process.exit(1);
  }
  console.log("rendered without error");
  process.exit(0);
}, 300);
