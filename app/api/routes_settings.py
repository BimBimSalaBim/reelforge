"""Settings: provider profiles, API keys, and the approval gates.

Everything here is guarded by `require_admin` because it accepts secrets. Keys
are written to `data/secrets.json`; nothing in this module ever returns a key
value, only where it came from and a masked form.

Writes land in `data/settings.yaml`, merged over the committed `config.yaml`,
which stays the hand-edited baseline and is mounted read-only in the container.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app import settings_store
from app.api.auth import access_mode, require_admin
from app.config import (
    LLM_DEFAULTS, LLM_ROLES, OPENAI_COMPATIBLE_ENDPOINTS, ROLE_PRESETS,
    TTS_DEFAULTS, get_config, is_hosted, profile_fields, reload_config,
)
from app.models.job import STAGE_ORDER

router = APIRouter(prefix="/api/settings", tags=["settings"],
                   dependencies=[Depends(require_admin)])

#: A variable *name*, not a value.
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalise_key_field(profile_name: str, value: str | None) -> tuple[str | None, str | None]:
    """Accept a pasted key in the variable-name field, and store it properly.

    The field wants the *name* of a variable, but pasting the key itself is the
    obvious mistake to make and it fails in the worst way: the key lands in
    `settings.yaml`, which is not the file with owner-only permissions, and the
    profile then has no key at all. Rather than reject it, the value is moved
    into the secrets store under a name derived from the profile.

    Returns (api_key_env, note) where note is a message for the caller.
    """
    value = (value or "").strip()
    if not value or ENV_NAME_RE.match(value):
        return (value or None), None

    derived = re.sub(r"[^A-Z0-9]+", "_", profile_name.upper()).strip("_") + "_API_KEY"
    settings_store.set_secret(derived, value)
    return derived, (
        f"That looked like an API key rather than a variable name, so it has been "
        f"stored securely as {derived} and the profile now points at it. Keys are "
        f"kept out of the settings file, which is not permission-restricted."
    )


# ------------------------------------------------------------- schemas ----
class ProfileIn(BaseModel):
    adapter: str
    label: str = ""
    model: str = ""
    base_url: str | None = None
    api_key_env: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class RoleIn(BaseModel):
    profile: str | None = None
    model: str | None = None
    temperature: float | None = None


class ApprovalIn(BaseModel):
    manual_stages: list[str]


class SecretIn(BaseModel):
    name: str
    value: str = ""


# --------------------------------------------------------------- read -----
def _profile_view(name: str, profile, *, active: bool, kind: str) -> dict:
    extra = profile.settings()
    key_env = extra.get("api_key_env")
    return {
        "name": name,
        "adapter": profile.adapter,
        "label": profile.display(),
        "model": extra.get("model", ""),
        "base_url": extra.get("base_url"),
        "active": active,
        "kind": kind,
        "api_key_env": key_env,
        "key": settings_store.secret_status(key_env) if key_env else None,
        "settings": extra,
        "fields": profile_fields(profile.adapter, kind),
    }


@router.get("")
def read_settings() -> dict:
    """Everything the settings screen renders. No secret values."""
    cfg = get_config()
    return {
        "access": access_mode(),
        "llm": {
            "active": cfg.llm.active,
            "profiles": [
                _profile_view(name, profile, active=name == cfg.llm.active, kind="llm")
                for name, profile in cfg.llm.profiles.items()
            ],
            "roles": {role: (cfg.llm.roles[role].model_dump(exclude_none=True)
                             if role in cfg.llm.roles else {})
                      for role in LLM_ROLES},
            "role_names": list(LLM_ROLES),
            "presets": ROLE_PRESETS,
            "adapters": sorted(LLM_DEFAULTS),
            "endpoints": OPENAI_COMPATIBLE_ENDPOINTS,
        },
        "tts": {
            "active": cfg.tts.active,
            "profiles": [
                _profile_view(name, profile, active=name == cfg.tts.active, kind="tts")
                for name, profile in cfg.tts.profiles.items()
            ],
            "adapters": sorted(TTS_DEFAULTS),
        },
        "approval": {
            "manual_stages": cfg.approval.manual_stages,
            "preset": cfg.approval.preset(),
            "stages": [s.value for s in STAGE_ORDER],
        },
        "content": cfg.content.model_dump(),
        "overlay_path": str(settings_store.settings_path()),
    }


# ------------------------------------------------------------ profiles ----
def _write(patch: dict) -> dict:
    settings_store.update_overlay(patch)
    reload_config()
    return read_settings()


def _replace(path: tuple[str, ...], value: Any) -> dict:
    """For maps whose absent keys are meaningful -- clearing role routing means
    removing entries, which a deep merge cannot express."""
    settings_store.replace_in_overlay(path, value)
    reload_config()
    return read_settings()


def _current(kind: str) -> dict:
    """The stored profile map, as plain data ready to patch.

    Read from the *merged* config rather than the overlay alone, so editing a
    profile that only exists in `config.yaml` copies it into the overlay
    complete rather than leaving a fragment that shadows half of it.
    """
    cfg = get_config()
    block = cfg.llm if kind == "llm" else cfg.tts
    return {name: {"adapter": profile.adapter, **profile.settings(),
                   **({"label": profile.label} if profile.label else {})}
            for name, profile in block.profiles.items()}


@router.put("/{kind}/profiles/{name}")
def upsert_profile(
    kind: Literal["llm", "tts"], name: str, payload: ProfileIn = Body(...)
) -> dict:
    """Create or update one profile.

    The adapter of an existing profile cannot change: its settings mean
    different things to different adapters, and silently reinterpreting a
    base_url or a voice id is worse than making you create a new profile.
    """
    if not name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(422, "a profile name may contain letters, digits, - and _")
    defaults = LLM_DEFAULTS if kind == "llm" else TTS_DEFAULTS
    if payload.adapter not in defaults:
        raise HTTPException(
            422, f"unknown adapter {payload.adapter!r}; known: {sorted(defaults)}")

    profiles = _current(kind)
    existing = profiles.get(name)
    if existing and existing.get("adapter") != payload.adapter:
        raise HTTPException(
            409,
            f"profile {name!r} uses the {existing['adapter']!r} adapter and cannot be "
            f"changed to {payload.adapter!r}. Create a new profile instead.",
        )

    entry = dict(defaults.get(payload.adapter, {})) if not existing else dict(existing)
    entry.update({k: v for k, v in payload.settings.items() if v is not None})
    entry["adapter"] = payload.adapter
    if payload.label:
        entry["label"] = payload.label
    if payload.model:
        entry["model"] = payload.model
    if payload.base_url is not None:
        entry["base_url"] = payload.base_url
    note = None
    if payload.api_key_env is not None:
        entry["api_key_env"], note = _normalise_key_field(name, payload.api_key_env)
        if entry["api_key_env"] is None:
            entry.pop("api_key_env", None)

    profiles[name] = entry
    result = _replace((kind, "profiles"), profiles)
    if note:
        result["notice"] = note
    return result


@router.delete("/{kind}/profiles/{name}")
def delete_profile(kind: Literal["llm", "tts"], name: str) -> dict:
    profiles = _current(kind)
    if name not in profiles:
        raise HTTPException(404, f"no profile named {name!r}")
    cfg = get_config()
    active = cfg.llm.active if kind == "llm" else cfg.tts.active
    if name == active:
        raise HTTPException(
            409,
            f"{name!r} is the profile in use. Select a different one first, so the "
            "pipeline is never left pointing at nothing.",
        )
    if kind == "tts" and name == "upload":
        raise HTTPException(
            409, "the upload profile cannot be removed: a job must always be able "
                 "to fall back to narration you supply yourself.")
    if len(profiles) <= 1:
        raise HTTPException(409, "this is the only profile; add another before "
                                 "removing it.")
    profiles.pop(name)

    roles = {role: binding for role, binding in
             ((r, cfg.llm.roles[r].model_dump(exclude_none=True))
              for r in cfg.llm.roles)
             if binding.get("profile") != name and binding.get("provider") != name}
    settings_store.replace_in_overlay((kind, "profiles"), profiles)
    if kind == "llm":
        settings_store.replace_in_overlay(("llm", "roles"), roles)
    reload_config()
    return read_settings()


@router.post("/{kind}/active")
def set_active(kind: Literal["llm", "tts"], name: str = Body(..., embed=True)) -> dict:
    if name not in _current(kind):
        raise HTTPException(404, f"no profile named {name!r}")
    return _write({kind: {"active": name}})


@router.post("/{kind}/profiles/{name}/test")
def test_profile(kind: Literal["llm", "tts"], name: str) -> dict:
    """Can this profile actually be reached? Costs nothing on any provider."""
    cfg = get_config()
    try:
        if kind == "llm":
            from app.providers.llm import build_llm

            return build_llm("content", cfg, {"profile": name}).health()
        from app.providers.tts import list_voices

        return list_voices(cfg, name)
    except Exception as exc:
        return {"reachable": False, "error": str(exc)[:300]}


@router.get("/tts/profiles/{name}/voices")
def profile_voices(name: str) -> dict:
    """The voices this profile can actually use.

    Populates the voice picker, so a voice is chosen from the account rather
    than an id pasted out of a dashboard -- which is how a wrong id ends up
    configured and only shows up as a failed synthesis.
    """
    from app.providers.tts import list_voices

    cfg = get_config()
    if name not in cfg.tts.profiles:
        raise HTTPException(404, f"no profile named {name!r}")
    try:
        found = list_voices(cfg, name)
    except Exception as exc:
        return {"voices": [], "reachable": False, "error": str(exc)[:200]}
    return {"voices": found.get("voices") or [],
            "selected": found.get("selected"),
            "reachable": found.get("reachable", False),
            "error": found.get("error")}


# --------------------------------------------------------------- roles ----
@router.put("/llm/roles")
def set_roles(roles: dict[str, RoleIn] = Body(...)) -> dict:
    profiles = _current("llm")
    cleaned: dict[str, Any] = {}
    for role, binding in roles.items():
        if role not in LLM_ROLES:
            raise HTTPException(422, f"unknown role {role!r}; known: {list(LLM_ROLES)}")
        if binding.profile and binding.profile not in profiles:
            raise HTTPException(404, f"no profile named {binding.profile!r}")
        entry = binding.model_dump(exclude_none=True)
        if entry:
            cleaned[role] = entry
    return _replace(("llm", "roles"), cleaned)


@router.post("/llm/roles/preset/{preset}")
def apply_role_preset(
    preset: str,
    hosted: str | None = Body(default=None, embed=True),
    local: str | None = Body(default=None, embed=True),
) -> dict:
    """Apply a ready-made routing.

    The presets name roles rather than profiles, because which profile is
    "hosted" depends on what you have configured. If you do not say, the first
    reachable cloud profile is used for hosted and the active one for local.
    """
    if preset not in ROLE_PRESETS:
        raise HTTPException(404, f"unknown preset {preset!r}; "
                                 f"known: {sorted(ROLE_PRESETS)}")
    cfg = get_config()
    profiles = cfg.llm.profiles

    if hosted is None:
        # prefer one whose key is actually set -- offering to route the two
        # expensive stages at a profile that cannot authenticate is no help
        candidates = [name for name, p in profiles.items() if is_hosted(p)]
        with_keys = [
            name for name in candidates
            if settings_store.secret_status(
                profiles[name].settings().get("api_key_env") or ""
            )["state"] == "set"
        ]
        hosted = (with_keys or candidates or [None])[0]
    if local is None:
        # the profile already in use, when it is a local one -- there may be
        # several configured and the active one is the one known to work
        active = profiles.get(cfg.llm.active)
        local = (cfg.llm.active if active and not is_hosted(active)
                 else next((name for name, p in profiles.items() if not is_hosted(p)),
                           cfg.llm.active))

    wanted = ROLE_PRESETS[preset]["roles"]
    if any(v == "__hosted__" for v in wanted.values()) and not hosted:
        raise HTTPException(
            409,
            "This preset routes the script and the storyboard to a hosted model, "
            "but no hosted profile is configured. Add an Anthropic or OpenAI "
            "profile first, or choose one explicitly.",
        )

    roles: dict[str, Any] = {}
    for role, target in wanted.items():
        name = hosted if target == "__hosted__" else local
        if name and name in profiles:
            roles[role] = {"profile": name}
    return _replace(("llm", "roles"), roles)


# ------------------------------------------------------------ approval ----
@router.put("/approval")
def set_approval(payload: ApprovalIn = Body(...)) -> dict:
    known = {s.value for s in STAGE_ORDER}
    unknown = [s for s in payload.manual_stages if s not in known]
    if unknown:
        raise HTTPException(422, f"unknown stage(s): {unknown}")
    ordered = [s.value for s in STAGE_ORDER if s.value in set(payload.manual_stages)]
    return _write({"approval": {"manual_stages": ordered}})


# ------------------------------------------------------------- secrets ----
@router.get("/secrets")
def list_secrets() -> dict:
    """Which keys are set, where each came from, and a masked form. No values.

    `shadowed` matters: a key set here has no effect while an environment
    variable of the same name exists, because the environment wins.
    """
    cfg = get_config()
    names: list[str] = []
    for block in (cfg.llm.profiles, cfg.tts.profiles):
        for profile in block.values():
            env = profile.settings().get("api_key_env")
            if env and env not in names:
                names.append(env)
    for extra in (cfg.ingest.github_token_env, cfg.ingest.hf_token_env):
        if extra not in names:
            names.append(extra)
    return {"secrets": [settings_store.secret_status(name) for name in names]}


@router.put("/secrets")
def set_secret(payload: SecretIn = Body(...)) -> dict:
    if not payload.name.strip():
        raise HTTPException(422, "a secret needs a variable name")
    settings_store.set_secret(payload.name.strip(), payload.value.strip())
    reload_config()
    return settings_store.secret_status(payload.name.strip())


@router.delete("/secrets/{name}")
def delete_secret(name: str) -> dict:
    settings_store.delete_secret(name)
    reload_config()
    return settings_store.secret_status(name)
