"""Persist settings written from the UI.

Three layers, each overriding the one before:

    config.yaml         the committed baseline, editable by hand, read-only
                        inside the container
    data/settings.yaml  what the UI writes -- non-secret overrides
    REELFORGE_* env     highest precedence, unchanged

Secrets live apart from all three, in `data/secrets.json` with 0600
permissions, and are never returned by any endpoint -- only a masked form is.
Keeping them out of `settings.yaml` means that file stays safe to read, copy or
paste somewhere while debugging.

`secret()` in `app.config` reads the environment first and falls back here, so
an existing `.env` setup keeps working exactly as before and a key set in the UI
simply fills a gap.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

import yaml

SETTINGS_NAME = "settings.yaml"
SECRETS_NAME = "secrets.json"
#: rw for the owner only; a secrets file the group can read is not a secrets file
SECRETS_MODE = stat.S_IRUSR | stat.S_IWUSR


def data_dir() -> Path:
    from app.config import REPO_ROOT

    raw = os.environ.get("REELFORGE_PATHS__DATA_DIR", "").strip()
    path = Path(raw) if raw else REPO_ROOT / "data"
    return path if path.is_absolute() else REPO_ROOT / path


def settings_path() -> Path:
    return data_dir() / SETTINGS_NAME


def secrets_path() -> Path:
    return data_dir() / SECRETS_NAME


def _atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ------------------------------------------------------------- overlay -----
def read_overlay() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        # a corrupt overlay must not make the app unstartable
        return {}


def write_overlay(data: dict[str, Any]) -> Path:
    path = settings_path()
    _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge, with `overlay` winning.

    Lists replace rather than concatenate: a settings file saying
    `manual_stages: [content]` means exactly that, not "the baseline plus
    content".
    """
    out = dict(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def update_overlay(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a patch into the stored overlay and persist it."""
    merged = merge(read_overlay(), patch)
    write_overlay(merged)
    return merged


def replace_in_overlay(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    """Set one subtree outright, discarding whatever was there.

    `update_overlay` deep-merges, which is right for editing a field but wrong
    for clearing a map: writing `{"llm": {"roles": {}}}` merges an empty dict
    into the existing roles and changes nothing. Clearing every role routing --
    what the "all local" preset does -- needs a replacement.
    """
    data = read_overlay()
    node = data
    for key in path[:-1]:
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise ValueError(f"{'.'.join(path)} is not a section")
    node[path[-1]] = value
    write_overlay(data)
    return data


# ------------------------------------------------------------- secrets -----
def read_secrets() -> dict[str, str]:
    path = secrets_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int))}


def write_secrets(values: dict[str, str]) -> Path:
    path = secrets_path()
    _atomic_write(path, json.dumps(values, indent=2), mode=SECRETS_MODE)
    return path


def set_secret(name: str, value: str) -> None:
    """Store one key. An empty value clears it."""
    values = read_secrets()
    if value:
        values[name] = value
    else:
        values.pop(name, None)
    write_secrets(values)


def delete_secret(name: str) -> bool:
    values = read_secrets()
    if name not in values:
        return False
    values.pop(name)
    write_secrets(values)
    return True


def mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def secret_status(name: str) -> dict[str, Any]:
    """Where a key comes from, and what it looks like -- never its value.

    The source matters when debugging: a key set in the UI has no effect while
    an environment variable of the same name is also set, because the
    environment wins.
    """
    env_value = (os.environ.get(name) or "").strip()
    stored = read_secrets().get(name, "")
    if env_value:
        return {"name": name, "state": "set", "source": "environment",
                "masked": mask(env_value),
                "shadowed": bool(stored)}
    if stored:
        return {"name": name, "state": "set", "source": "settings",
                "masked": mask(stored), "shadowed": False}
    return {"name": name, "state": "unset", "source": None,
            "masked": "", "shadowed": False}


def fingerprint() -> tuple[float, ...]:
    """Modification times of every file that feeds configuration.

    The API and the workers are separate processes, so a settings change made in
    one has to be noticed by the others. Comparing mtimes does that with no IPC
    and no message bus -- each process reloads when it sees the files move.
    """
    from app.config import config_path

    out = []
    for path in (config_path(), settings_path(), secrets_path()):
        try:
            out.append(path.stat().st_mtime_ns / 1e9)
        except OSError:
            out.append(0.0)
    return tuple(out)
