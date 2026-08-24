"""Rewrite the inputs of a ComfyUI API-format workflow.

A workflow exported with "Save (API format)" is a flat dict of
`node_id -> {"class_type", "inputs", "_meta"}`, where an input is either a
literal or a link `[source_node_id, output_index]`. Submitting one is a POST
of that dict; using one for our purposes is finding the handful of inputs that
matter -- the prompt, the size, the seed, the duration -- and replacing them.

Two ways to name those inputs. A node map from the profile
(`{"prompt": "405:376", "seconds": "405:362"}`) is exact and is what the
shipped workflows use. Without one, `detect()` walks the graph: the positive
prompt is whatever text node feeds the sampler's `positive` input, the seed is
any literal `seed`/`noise_seed`, the size is the empty-latent node, and so on.
Detection is good enough for a plain graph; a prompt behind a switch node
(the LTX workflow's enhancer toggle) is why the map exists.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

#: Inputs worth following when walking back from a sampler to the text that
#: feeds it, in the order a branch is preferred. `on_false` before `on_true`
#: because the false branch of a switch is the raw prompt; the true branch is
#: an enhancer that reads the same raw prompt anyway.
TEXT_INPUTS = ("text", "prompt", "on_false", "value", "string", "on_true")

SAMPLER_INPUTS = ("positive", "negative")
SIZE_CLASSES = ("EmptySD3LatentImage", "EmptyLatentImage", "EmptyHunyuanLatentVideo",
                "EmptyLTXVLatentVideo")
SAVE_CLASSES = {"image": ("SaveImage", "SaveAnimatedWEBP", "SaveAnimatedPNG"),
                "video": ("SaveVideo", "VHS_VideoCombine", "SaveWEBM"),
                "audio": ("SaveAudio", "SaveAudioMP3", "SaveAudioOpus", "SaveAudioFLAC")}
AUDIO_LATENT_CLASSES = ("EmptyLatentAudio",)

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")
AUDIO_EXT = (".mp3", ".wav", ".flac", ".opus", ".ogg", ".m4a")
EXT_FOR = {"image": IMAGE_EXT, "video": VIDEO_EXT, "audio": AUDIO_EXT}


class WorkflowError(ValueError):
    pass


def is_link(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], str) and isinstance(value[1], int))


def load(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise WorkflowError(f"workflow not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise WorkflowError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "nodes" in data:
        raise WorkflowError(
            f"{path.name} is a UI workflow, not an API one. In ComfyUI use "
            "Workflow > Export (API) and point the profile at that file."
        )
    for key, node in data.items():
        if not isinstance(node, dict) or "class_type" not in node:
            raise WorkflowError(f"{path.name}: node {key!r} has no class_type")
    return data


class Graph:
    """Read-only questions about a workflow."""

    def __init__(self, nodes: dict[str, Any]):
        self.nodes = nodes

    def of(self, *classes: str) -> list[str]:
        return [k for k, n in self.nodes.items() if n.get("class_type") in classes]

    def titled(self, *fragments: str) -> list[str]:
        out = []
        for key, node in self.nodes.items():
            title = str((node.get("_meta") or {}).get("title", "")).lower()
            if any(f.lower() in title for f in fragments):
                out.append(key)
        return out

    def inputs(self, key: str) -> dict[str, Any]:
        return self.nodes[key].setdefault("inputs", {})

    def text_node(self, start: str, depth: int = 8) -> tuple[str, str] | None:
        """Walk back from `start` to the node holding a literal string."""
        seen = set()
        key = start
        while key in self.nodes and key not in seen and depth > 0:
            seen.add(key)
            depth -= 1
            inputs = self.inputs(key)
            for name in TEXT_INPUTS:
                if name in inputs and isinstance(inputs[name], str):
                    return key, name
            nxt = next((inputs[n][0] for n in TEXT_INPUTS
                        if n in inputs and is_link(inputs[n])), None)
            if nxt is None:
                return None
            key = nxt
        return None

    def prompt_nodes(self) -> dict[str, tuple[str, str]]:
        """`positive`/`negative` -> (node, input) holding the literal text."""
        out: dict[str, tuple[str, str]] = {}
        for key, node in self.nodes.items():
            inputs = node.get("inputs") or {}
            for role in SAMPLER_INPUTS:
                if role in out or not is_link(inputs.get(role)):
                    continue
                found = self.text_node(inputs[role][0])
                if found:
                    out[role] = found
        return out

    def seed_nodes(self) -> list[tuple[str, str]]:
        out = []
        for key, node in self.nodes.items():
            for name in ("seed", "noise_seed"):
                if isinstance((node.get("inputs") or {}).get(name), int):
                    out.append((key, name))
        return out

    def size_node(self) -> str | None:
        for key in self.of(*SIZE_CLASSES):
            inputs = self.inputs(key)
            if isinstance(inputs.get("width"), int) and isinstance(inputs.get("height"), int):
                return key
        return None

    def save_node(self, kind: str) -> str | None:
        found = self.of(*SAVE_CLASSES[kind])
        return found[0] if found else None


# ------------------------------------------------------------ detection ---
def detect(nodes: dict[str, Any], kind: str) -> dict[str, str]:
    """Best-effort node map, the same shape as the profile's `*_nodes`."""
    g = Graph(nodes)
    found: dict[str, str] = {}
    prompts = g.prompt_nodes()
    if "positive" in prompts:
        found["prompt"] = prompts["positive"][0]
    if "negative" in prompts:
        found["negative"] = prompts["negative"][0]
    seeds = g.seed_nodes()
    if seeds:
        found["seed"] = seeds[0][0]
    save = g.save_node(kind)
    if save:
        found["save"] = save
    if kind == "image":
        size = g.size_node()
        if size:
            found["size"] = size
        for key in g.titled("lightning", "4 step", "4-step", "lora"):
            if g.nodes[key].get("class_type") == "PrimitiveBoolean":
                found["lightning"] = key
                break
    else:
        for role, words in (("seconds", ("duration", "seconds", "length")),
                            ("fps", ("frame rate", "fps", "framerate"))):
            for key in g.titled(*words):
                if g.nodes[key].get("class_type") == "PrimitiveInt" \
                        and isinstance(g.inputs(key).get("value"), int):
                    found[role] = key
                    break
        for key in g.titled("enhance"):
            if g.nodes[key].get("class_type") == "PrimitiveBoolean":
                found["enhancer"] = key
                break
        res = g.of("ResolutionSelector")
        if res:
            found["resolution"] = res[0]
    if kind == "audio":
        # `seconds` is either literal on the latent node or fed by a primitive
        for key in g.of(*AUDIO_LATENT_CLASSES):
            value = g.inputs(key).get("seconds")
            if isinstance(value, (int, float)):
                found["seconds"] = key
            elif is_link(value):
                found["seconds"] = value[0]
            break
        # the SA3 workflow's Music / Instrument / SFX / One-shot selector
        for key, node in nodes.items():
            inputs = node.get("inputs") or {}
            if "choice" in inputs and any(
                    str(v).lower() in ("music", "sfx", "one-shot") for v in inputs.values()):
                found["category"] = key
                break
        for key in g.titled("reprompt", "enhance"):
            if g.nodes[key].get("class_type") == "PrimitiveBoolean":
                found["enhancer"] = key
                break
    return found


def describe(nodes: dict[str, Any], node_map: dict[str, str]) -> dict[str, str]:
    """`role -> "id class (title)"` for the health report."""
    out = {}
    for role, key in node_map.items():
        node = nodes.get(key)
        if not node:
            out[role] = f"{key} (missing)"
            continue
        title = (node.get("_meta") or {}).get("title") or ""
        out[role] = f"{key} {node.get('class_type')}" + (f" ({title})" if title else "")
    return out


# -------------------------------------------------------------- patching ---
def _set_text(g: Graph, key: str, value: str) -> None:
    """Put `value` into whichever string input the node actually carries."""
    inputs = g.inputs(key)
    for name in TEXT_INPUTS:
        if name in inputs and isinstance(inputs[name], str):
            inputs[name] = value
            return
    # the map pointed at a node upstream of a switch: walk to the literal
    found = g.text_node(key)
    if not found:
        raise WorkflowError(f"node {key} has no text input to set")
    g.inputs(found[0])[found[1]] = value


def _append_text(g: Graph, key: str, extra: str) -> None:
    """Add to a text input rather than replace it: the workflow author's
    negative prompt stays, ours joins it."""
    found = g.text_node(key)
    if not found:
        raise WorkflowError(f"node {key} has no text input to extend")
    node, name = found
    current = str(g.inputs(node).get(name) or "").strip().rstrip(",")
    g.inputs(node)[name] = f"{current}, {extra}" if current else extra


def _set_seed(g: Graph, key: str | None, seed: int) -> int:
    """Every seed in the graph, not just the mapped one: the LTX workflow has
    two noise sources, and leaving one fixed makes every clip open the same
    way."""
    count = 0
    for node, name in g.seed_nodes():
        g.inputs(node)[name] = seed
        count += 1
    if key and key in g.nodes:
        inputs = g.inputs(key)
        for name in ("seed", "noise_seed"):
            if name in inputs:
                inputs[name] = seed
    return count


def _set_bool(g: Graph, key: str | None, value: bool) -> None:
    if key and key in g.nodes:
        g.inputs(key)["value"] = bool(value)


def _set_prefix(g: Graph, key: str | None, prefix: str) -> None:
    if key and key in g.nodes and "filename_prefix" in g.inputs(key):
        g.inputs(key)["filename_prefix"] = prefix


def _resolve_map(nodes: dict[str, Any], kind: str, node_map: dict[str, str] | None) -> dict[str, str]:
    found = detect(nodes, kind)
    found.update({k: v for k, v in (node_map or {}).items() if v})
    if "prompt" not in found:
        raise WorkflowError(
            f"could not find the {kind} workflow's prompt node: no text node feeds "
            "a sampler's `positive` input. Name it in the profile's node map."
        )
    return found


def patch_image(nodes: dict[str, Any], node_map: dict[str, str] | None, *,
                prompt: str, negative: str | None, width: int, height: int,
                seed: int, lightning: bool | None, prefix: str) -> dict[str, Any]:
    nodes = copy.deepcopy(nodes)
    g = Graph(nodes)
    m = _resolve_map(nodes, "image", node_map)
    _set_text(g, m["prompt"], prompt)
    if negative and m.get("negative"):
        _append_text(g, m["negative"], negative)
    if m.get("size"):
        g.inputs(m["size"])["width"] = int(width)
        g.inputs(m["size"])["height"] = int(height)
    _set_seed(g, m.get("seed"), seed)
    if lightning is not None:
        _set_bool(g, m.get("lightning"), lightning)
    _set_prefix(g, m.get("save"), prefix)
    return nodes


def patch_video(nodes: dict[str, Any], node_map: dict[str, str] | None, *,
                prompt: str, negative: str | None, seconds: float, fps: int,
                seed: int, enhancer: bool | None, prefix: str) -> dict[str, Any]:
    nodes = copy.deepcopy(nodes)
    g = Graph(nodes)
    m = _resolve_map(nodes, "video", node_map)
    _set_text(g, m["prompt"], prompt)
    if negative and m.get("negative"):
        _append_text(g, m["negative"], negative)
    if m.get("seconds") and m["seconds"] in nodes:
        g.inputs(m["seconds"])["value"] = int(round(seconds))
    if m.get("fps") and m["fps"] in nodes:
        g.inputs(m["fps"])["value"] = int(fps)
    _set_seed(g, m.get("seed"), seed)
    if enhancer is not None:
        _set_bool(g, m.get("enhancer"), enhancer)
    _set_prefix(g, m.get("save"), prefix)
    return nodes


def patch_audio(nodes: dict[str, Any], node_map: dict[str, str] | None, *,
                prompt: str, negative: str | None, seconds: float, seed: int,
                category: str | None, enhancer: bool | None, prefix: str) -> dict[str, Any]:
    nodes = copy.deepcopy(nodes)
    g = Graph(nodes)
    m = _resolve_map(nodes, "audio", node_map)
    _set_text(g, m["prompt"], prompt)
    if negative is not None and m.get("negative"):
        _set_text(g, m["negative"], negative)
    key = m.get("seconds")
    if key and key in nodes:
        inputs = g.inputs(key)
        if "seconds" in inputs and not is_link(inputs["seconds"]):
            inputs["seconds"] = float(seconds)
        elif "value" in inputs:
            inputs["value"] = float(seconds) if isinstance(inputs["value"], float) else int(round(seconds))
    if category and m.get("category") and m["category"] in nodes:
        inputs = g.inputs(m["category"])
        options = [v for k, v in inputs.items() if k.startswith("option") and v]
        if category in options:
            inputs["choice"] = category
            inputs["index"] = options.index(category)
    _set_seed(g, m.get("seed"), seed)
    if enhancer is not None:
        _set_bool(g, m.get("enhancer"), enhancer)
    _set_prefix(g, m.get("save"), prefix)
    return nodes


def workflow_fps(nodes: dict[str, Any], node_map: dict[str, str] | None) -> int | None:
    """The frame rate a video workflow will actually produce, if it says."""
    m = detect(nodes, "video")
    m.update({k: v for k, v in (node_map or {}).items() if v})
    key = m.get("fps")
    if key and key in nodes:
        value = (nodes[key].get("inputs") or {}).get("value")
        if isinstance(value, int):
            return value
    return None
