# Configuration

Three layers, each overriding the one above:

```
config.yaml            the committed baseline; mounted read-only in the container
data/settings.yaml     what the Settings UI writes; merged over the baseline
environment variables  REELFORGE_<SECTION>__<KEY>, and every API key
```

Because UI edits land in `data/settings.yaml`, the file you edit by hand stays
yours and pulling a new `config.yaml` never overwrites your setup.

**Keys are never written to `config.yaml`.** It names the environment variable
(`api_key_env`); the value comes from the environment or from
`data/secrets.json`, which is created `0600` and is never returned by any
endpoint — only its origin and a masked form.

---

## Profiles

Providers are profiles, not fixed blocks, so several can share one adapter. A
single OpenAI-compatible adapter reaches OpenAI, vLLM, LM Studio, Together, Groq,
OpenRouter and Azure alike — they differ only by `base_url`.

```yaml
llm:
  active: local-vllm
  profiles:
    local-vllm: {adapter: openai,  base_url: "http://localhost:8000/v1",
                 model: qwen, json_mode: text}
    ollama:     {adapter: ollama,  base_url: "http://localhost:11434",
                 model: "qwen2.5:7b-instruct-q4_K_M"}
    hosted:     {adapter: openai,  base_url: "https://openrouter.ai/api/v1",
                 model: "...", api_key_env: OPENROUTER_API_KEY}
  roles:                        # per-stage routing; empty means "use active"
    content:    {profile: hosted}
    storyboard: {profile: hosted}

tts:
  active: upload
  profiles:
    upload:     {adapter: upload}
    elevenlabs: {adapter: elevenlabs, voice_id: "...",
                 api_key_env: ELEVENLABS_API_KEY}
```

Available LLM adapters: `openai` (any OpenAI-compatible endpoint), `ollama`,
`anthropic`, `fake` (for tests).
TTS adapters: `upload`, `elevenlabs`, `openai`, `local` (Kokoro/Piper), `say`
(macOS, development only).

An older `config.yaml` using the pre-profiles shape — a `provider:` key beside
fixed per-vendor blocks — is still read and converted automatically.

Any value can be overridden by environment:

```bash
REELFORGE_LLM__PROVIDER=ollama
REELFORGE_RENDER__WORKERS=4
```

---

## Model routing

The stages are not the same kind of work, so they need not use the same model.
Three presets:

| Preset | What it does |
|---|---|
| All local | Everything through Ollama. Free and offline; the script reads like a 7B model wrote it |
| **Hybrid** | A strong hosted model for the script and the storyboard, local for the rest. **Recommended** |
| All hosted | Every stage hosted. Best results, still cents per reel |

Hybrid is the one worth understanding. Writing the script and writing a
storyboard module are where model quality shows. Extracting a fact sheet or
choosing a palette are structured tasks with validators behind them, and a small
local model handles those fine.

---

## `json_mode` matters more than it looks

**Reasoning models must not use `json_schema`.** Grammar-constrained decoding
forces JSON from the first token, leaving the model no room to think, and it
stalls. Measured against a local vLLM: over five minutes with no result under
`json_schema`, versus 40 seconds under `text`.

| Mode | Use for |
|---|---|
| `json_schema` | An instruct model. Grammar-constrained, exact |
| `json_object` | Valid JSON, shape unenforced |
| `text` | **A reasoning model.** Schema in the prompt, JSON recovered from the reply |

The adapter falls through the list in order, so a server that rejects one mode
still works.

---

## Script generation

`content.script_mode` chooses how the narration is written:

| Mode | |
|---|---|
| `whole` | One call for the whole script. Best narrative flow; use with a strong model |
| `per_scene` | An outline call, then one call per scene, with continuation rounds |
| `auto` *(default)* | One whole-script attempt, then switch approach rather than ask the same way again |

Measured on `qwen2.5:7b-instruct`: the single-pass ask stalled at 30–48 words
across every retry and phrasing; per-scene reached 92–100 words in under twenty
seconds. A model that returns 40 words when asked for 95 returns 25 when asked
for 25.

Accumulated output is de-duplicated, fragments are merged into breath-sized
phrases, and split grouped numbers like `80, 000` are repaired.

Runtime targets live beside it:

```yaml
content:
  script_mode: auto
  target_seconds_min: 36.0
  target_seconds_max: 44.0
  max_attempts: 3
```

Keep a reel 30–45 seconds. One file then serves Reels (≤90 s) and Shorts (≤3 min).

---

## Approval gates

```yaml
approval:
  manual_stages: [content, storyboard]
```

Choose which stages stop for you. Presets for all-manual and all-auto are in
Settings, and a per-job setting overrides the saved default.

---

## Per-reel settings

Two things are chosen per reel rather than globally, on the **New reel** form:

- **Captions.** Burned-in, word-synced captions are the single highest-leverage
  thing in the pipeline, because most feed views start muted. Both platforms also
  auto-caption, so this is a real choice.
- **Fact validation.** Every claim on screen is a hostage. The checker compares
  what the script says against what `ingest` actually found.

---

## Multiple ElevenLabs keys

Credits are metered per character and a narration is a dozen calls, so an
allowance can run out mid-job. List several keys and the next takes over
automatically:

```bash
# .env — either comma-separated in one variable...
ELEVENLABS_API_KEY=key_one,key_two

# ...or separate variables named in config.yaml under api_key_envs
ELEVENLABS_API_KEY_2=
```

```yaml
tts:
  elevenlabs:
    api_key_envs: [ELEVENLABS_API_KEY, ELEVENLABS_API_KEY_2, ELEVENLABS_API_KEY_3]
    active_key: null                 # null rotates; a label or index pins one
    max_characters_per_job: 4000     # a 40 s reel is ~550-700 characters
```

`max_characters_per_job` exists so an accidentally long job fails **before** it
spends anything. `GET /api/config/providers` reports each key's remaining balance
without spending anything.

---

## Rendering

```yaml
render:
  chunk_seconds: 4.0      # must be a whole number of 2 s GOPs
  workers: 0              # 0 = decide from the machine (cores - 1, capped at 8)
  safe_encode: false      # true = single-process pipe, exactly like make.sh
  fps: 30
  width: 1080
  height: 1920
```

Each worker runs a renderer *and* an encoder, so setting `workers` to twice the
core count does not go faster — it thrashes.

`safe_encode: true` runs the reference path, byte-for-byte the command in
`video/make.sh`. Use it to check a chunked result against.

### Encode settings — do not drift

```
1080x1920 · 30 fps · H.264 High @ 4.1 · yuv420p · CRF 18
closed GOP every 2 s · bt709 tagged
AAC-LC 192 kbps 48 kHz stereo · +faststart
audio normalised to -14 LUFS / -1.5 dBTP
```

−14 LUFS is what both platforms normalise to: hit it and neither turns the video
down. **The bt709 tags matter** — untagged, both platforms render the colours
washed out.

---

## Storyboard validation

```yaml
storyboard:
  max_repair_attempts: 3
  vision_review: false           # needs a multimodal provider
  fallback_to_template: true
  smoke_frames: 16
  smoke_timeout_seconds: 90
  memory_limit_mb: 3072
```

`fallback_to_template: true` is what guarantees a job always produces a video:
when generation exhausts its repair budget, the job renders through
`safe-deterministic` instead.

---

## Ingest

```yaml
ingest:
  github_token_env: GITHUB_TOKEN
  hf_token_env: HUGGINGFACE_TOKEN
  timeout_seconds: 30
  readme_max_chars: 60000
```

A GitHub token is optional and raises the rate limit from 60 to 5000 requests an
hour. A Hugging Face token is only needed for gated repositories.

---

## Securing the settings API

The settings API accepts API keys, so it is guarded:

| Mode | When | Who can change settings |
|---|---|---|
| **loopback** *(default)* | `REELFORGE_ADMIN_TOKEN` empty | This machine only |
| **token** | `REELFORGE_ADMIN_TOKEN` set | Any host presenting that bearer token |

Compose binds to `127.0.0.1` to match the default. Set the token before
publishing the port beyond localhost.
