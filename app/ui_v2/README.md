# ui_v2

The current web UI. Separate pages, no build step, no CDN, no framework — the
app must keep working offline and `node --check` is the only JavaScript
verification this repo has.

## Rules

- **No `style=` in any `.html` file.** JavaScript may set computed geometry (the
  frame scale, a panel height, a progress width); everything else is a class.
  Enforced by `tests/test_ui_v2.py`.
- **No raw colour below the `:root` block in `app.css`.** The v1 stylesheet had
  fourteen hexes outside its own token set, which is why nothing in it could be
  re-themed and nothing was consistent.
- **Classic scripts, not ES modules.** Each file is an IIFE hanging one object
  off `window.RF`. `node --check` runs on these with no flags; checking an ES
  module needs an experimental flag, and `.mjs` is served as `text/plain` on some
  hosts.
- **Never retype a Python constant.** Frame geometry comes from
  `GET /api/images/frame`. Reel length comes from the stage that computed it.

## Adding a page

Copy an existing page's `<head>`, add `static/<page>.js` ending in
`RF.shell.ready(init)`, and link it from `shell.js`'s `NAV` if it belongs in the
header. `tests/test_ui_v2.py` finds new pages and scripts on disk automatically:
it will serve them, check their asset references resolve, and parse their
JavaScript.

## Shared modules

| file | what it is |
|---|---|
| `dom.js` | `el()` hyperscript, formatters, toasts, dialogs, skeletons |
| `api.js` | fetch wrapper, `ApiError`, SSE with loss detection, visibility-aware polling |
| `stages.js` | stage labels and blurbs, refreshed from `GET /api/stages` |
| `queue.js` | normalises the queue payload; understands the old shape too |
| `reelspec.js` | frame geometry and crop maths, loaded from the API |
| `frame.js` | the 9:16 reel-frame preview, which is also the cropper |
| `imagestage.js` | screenshots held client-side before a job exists |
| `shell.js` | the shared header, and `ready()` |

`el()` is not a style preference. The v1 UI concatenated HTML and called `esc()`
by hand at about ninety sites; one omission turns a repository name or an
LLM-authored caption into script injection. Here the default is `textContent`.

## The old UI

`app/ui/dist/index.html` is frozen and still served at `/`. Nothing is added to
it and no code is shared with it — sharing would couple the thing being replaced
to its replacement, which is the usual way a migration stops halfway.
