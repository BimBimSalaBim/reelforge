# Architecture

Two halves. `video/` is a hand-run renderer that turns a script and a voice
recording into a finished vertical video. `app/` wraps it in a job-based service
and **does not modify it**.

---

## The filesystem is the database

A job is a directory. `job.json` is its state; every artefact sits beside it as a
file you can open, diff and edit.

```
data/jobs/<id>/
  job.json         state machine, queue position, per-stage records
  facts.json       what ingest found
  content.json     script, phrases, fact sheet, cover spec, platform copy
  storyboards/     the generated module
  build/           timing, mixes, logs
  out/             the delivery bundle
```

Writes go through an atomic helper — temp file plus `os.replace` — so a job is
never half-written. There is no migration step and no schema to keep in sync.

This is also why the queue needs no recovery code: queue state lives in
`job.json`, so it is rebuilt by scanning jobs and survives a restart intact.

---

## Stages

Nine stages, defined once in `app/stages/`. A single walker runs them:

```python
def walk(job_id, store=None, *, until=None, should_stop=None) -> str:
    """-> "complete" | "review:<stage>" | "failed:<stage>"
          | "until:<stage>" | "cancelled" | "gone" """
```

Both the inline runner and the Celery task call it, so there is one definition of
what a stage is. They were near-duplicates once and had already drifted: a failed
stage never published a pipeline-failed event in one of them, and the browser was
told the stage failed but never that the pipeline had stopped.

Re-running a stage invalidates everything downstream, so an edited script cannot
leave a video rendered from the previous one.

---

## The queue

One job runs end to end at a time. About 76% of an 11.3-minute run is the two LLM
stages — `content` at ~207 s and `storyboard` at ~309 s median — and two at once
is two workloads against one GPU.

| Module | Responsibility |
|---|---|
| `app/queue_store.py` | All state, no threads. `claim_next` holds the whole concurrency invariant |
| `app/scheduler.py` | One thread. `tick()` is synchronous, so tests need no sleeps |
| `app/eta.py` | Estimates from real stage medians already on disk |

Design notes worth keeping:

- **A single-stage run or a retry joins the queue at the front** rather than
  bypassing it. Bypassing would be the second concurrent LLM call the queue
  exists to prevent.
- **Cancel takes effect at a stage boundary**, never mid-stage.
- **A job that was running when the process died leaves the queue** rather than
  going back into it — re-queueing would send it into the stage that just died,
  for ever.
- **Two consecutive failures pause the queue.** That is a broken model server, not
  two broken reels.
- The queue takes a file lock, but the app already assumes one process. Run
  `uvicorn --workers 1`.
- Under Celery the broker owns concurrency; reorder and pause return `501`.

---

## Driving `video/` without touching it

`video/` is treated as read-only. Two mechanisms make that possible, and both
exist because of a real constraint.

### Per-job symlink farm

`align.py` and `timing.py` resolve `build/` from their own `__file__`, and
`align.py` uses one fixed scratch file — so concurrent jobs would collide on
disk. `app/render/workspace.py` builds a directory of symlinks to the real
modules, which moves `HERE` into the job directory and gives each job a private
`build/`.

This works because `os.path.abspath` normalises a path but does **not** resolve
symlinks.

### Shims

Thin wrappers that patch a module global and delegate:

| | |
|---|---|
| `shim_render` | Replaces `kit.f` / `kit.m` with bundled open-source faces before `sbkit` is imported |
| `shim_align` | Merges the generated pronunciation map into `align.SPOKEN` |
| `shim_cover` | Injects a generated spec into `covers.SPECS` |

---

## Generated storyboards

The model writes a real Python module against `sbkit`. Eight checks decide
whether it is worth minutes of rendering, cheapest first; each failure becomes
the repair prompt.

1. It parses.
2. Imports are on the allowlist; no `exec`, `open`, `subprocess`.
3. The module contract, and `TOTAL` agrees with the narration.
4. **Every cue word was actually spoken.**
5. The scene table is contiguous and paced.
6. Sample frames render, in a limited subprocess.
7. Nothing legible sits under the platform UI.
8. Optionally, a multimodal model looks at the frames.

Check 4 earns its keep. `Timing.ws()` raises on an unknown word — deliberately,
so a typo is never a silent mistiming — and naming a word that was never spoken
is the likeliest mistake a model makes. Catching it statically costs
milliseconds; catching it at render time costs a full repair round. The check
suggests the nearest real word.

`ALLOWED_IMPORTS` is `{kit, sbkit, timing, …}`. It deliberately excludes
`ledger`, so a generated storyboard cannot use the second design language.

**The sandbox contains buggy code, not hostile code.** Resource limits and the
import allowlist are defence in depth against a bad loop, not a boundary against
an adversary. For that, run the renderer with no network and a read-only root.

---

## Chunked rendering

Rendering is 3–9 fps, so a 40-second reel is 7–9 minutes single-process.
`render.py --only T0 T1` is the seam: chunks are cut on whole 2-second GOP
boundaries so the concat demuxer joins them with `-c copy`, and the joined frame
count is asserted against `round(TOTAL × 30)` **before** audio is attached. About
60 seconds instead of 7–9 minutes.

That assertion matters. A broken pipe otherwise leaves a shorter, playable, wrong
file — and the verifier used to pass it, because nothing in it decoded video. It
now decodes every frame and compares against the container duration.

---

## Reel geometry lives in Python

The frame constants exist in `app/images.py`, inside the emitted storyboard
template, and in `video/sbkit.py` (read-only). `GET /api/images/frame` serves
them to the browser so the upload preview cannot drift from the renderer.

Never retype them into JavaScript. Three of them moved in a single afternoon.

---

## Two design languages

Both share `kit.py`, the renderer, the mixer and the encode settings, and nothing
else.

| | **Bloom** (`sbkit.py`) | **Ledger** (`ledger.py`) |
|---|---|---|
| layout | centred column | left-aligned off a spine at x 180 |
| surfaces | rounded cards, radial glow | hairline rules, whitespace, no glow |
| scenes | replace one another | a scene index accumulates in the gutter |
| entrance | fade up + slide | horizontal wipe out of the spine |
| ground | radial blooms + falloff | flat + faint grid |
| cover | `covers.render` / `render_stack` | `covers.render_ledger` |

`ledger.py` imports `kit` and nothing else — never `sbkit` — so the two share no
module state. Captions are identical in both: bottom centre, word-synced. Ledger
restyles them but does not move them, because most views start muted and that
placement is the highest-leverage thing here.

---

## The UI

Two, deliberately.

**`/v2`** is the current one: separate HTML pages, no build step, no CDN, no
router. Scripts are classic (an IIFE on `window.RF`), which means `node --check`
runs on them with no flags — the only JavaScript verification this project has.
`.mjs` is avoided because its MIME type is unreliable when served from disk.

Adding a page is dropping an `.html` into `app/ui_v2/` and a matching
`static/<page>.js`; the test suite picks it up automatically.

**`/`** is the original single-file UI. It is **frozen** — the escape hatch while
v2 settles. Sharing code with it would couple the thing being replaced to its
replacement, which is the usual way a migration stops halfway.

Two details worth knowing:

- **Route order.** `GET /{path:path}` matches everything, so anything registered
  after it is unreachable. `/v2` is registered first, and a test asserts it.
- **Theme before first paint.** `theme.js` is synchronous and stamps
  `data-theme` on the root element, so there is no flash of the wrong theme.

---

## Testing

```bash
python -m pytest -q
```

`tests/fixtures/render_page.js` renders a v2 page under a DOM stub against
captured API payloads and fails if the page renders an error callout. It has
caught bugs `node --check` cannot see.

The stub implements `Node`, because `el()` checks `child instanceof Node` — an
earlier version used plain objects, so every element stringified to
`[object Object]` and a broken page reported as fine.

Tests build `TestClient(app)` **without** a `with` block, so the lifespan never
fires and no scheduler leaks into the suite.
