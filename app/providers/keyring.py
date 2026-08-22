"""A rotating pool of API keys.

Metered APIs fail in a way retrying cannot fix: once a key's monthly character
allowance is gone, every call returns 429 until the quota resets. Rotating to a
second key is the only thing that helps, and the switch has to happen mid-job --
a narration is a dozen separate calls and the allowance can run out between two
of them.

Keys are held by *name*, never by value, in anything that gets logged or
returned. The value is read from the environment at call time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator


class NoKeysAvailable(RuntimeError):
    pass


@dataclass
class KeySlot:
    label: str          # the env var name, or "<VAR>#2" for a packed list
    value: str
    exhausted_at: datetime | None = None
    rejected_at: datetime | None = None
    failures: int = 0
    calls: int = 0

    @property
    def usable(self) -> bool:
        return self.exhausted_at is None and self.rejected_at is None

    @property
    def state(self) -> str:
        if self.rejected_at:
            return "rejected"
        if self.exhausted_at:
            return "exhausted"
        return "ready"

    def masked(self) -> str:
        if len(self.value) <= 8:
            return "*" * len(self.value)
        return f"{self.value[:4]}...{self.value[-4:]}"

    def as_dict(self) -> dict:
        return {"label": self.label, "state": self.state, "key": self.masked(),
                "calls": self.calls, "failures": self.failures}


@dataclass
class KeyRing:
    """Ordered pool with a current selection.

    Automatic rotation advances past keys the provider has told us are finished.
    A pinned selection disables rotation, so a deliberate manual choice is not
    silently overridden.
    """

    slots: list[KeySlot] = field(default_factory=list)
    index: int = 0
    pinned: bool = False

    # ---- construction ---------------------------------------------------
    @classmethod
    def from_env(
        cls, env_names: list[str] | str, *, active: str | int | None = None
    ) -> "KeyRing":
        """Read keys by variable name, from the environment or the settings store.

        Resolution matches `app.config.secret`: the environment first, then a key
        saved through the settings UI. Reading `os.environ` alone was a bug --
        a key set in the UI was stored correctly and reported as set, and the
        provider still refused to start because this never looked at it.

        A variable may hold several keys separated by commas, so a single
        `ELEVENLABS_API_KEY=k1,k2,k3` configures a rotation pool with no extra
        configuration.
        """
        from app.config import secret

        if isinstance(env_names, str):
            env_names = [env_names]
        slots: list[KeySlot] = []
        for name in env_names:
            raw = (secret(name) or "").strip()
            if not raw:
                continue
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            for position, value in enumerate(parts):
                label = name if len(parts) == 1 else f"{name}#{position + 1}"
                slots.append(KeySlot(label=label, value=value))

        ring = cls(slots=slots)
        if active is not None:
            ring.select(active)
        return ring

    # ---- selection ------------------------------------------------------
    def select(self, which: str | int) -> KeySlot:
        """Pin a specific key by label or position. Disables rotation."""
        if isinstance(which, int):
            if not 0 <= which < len(self.slots):
                raise NoKeysAvailable(f"no key at position {which}")
            self.index = which
        else:
            matches = [i for i, s in enumerate(self.slots) if s.label == which]
            if not matches:
                raise NoKeysAvailable(
                    f"no key labelled {which!r}; have {[s.label for s in self.slots]}"
                )
            self.index = matches[0]
        self.pinned = True
        return self.slots[self.index]

    def auto(self) -> "KeyRing":
        """Release a pin and go back to rotating."""
        self.pinned = False
        return self

    @property
    def current(self) -> KeySlot:
        if not self.slots:
            raise NoKeysAvailable(
                "no API key found. Set the variable named by `api_key_env` (or list "
                "several in `api_key_envs`) in your .env file."
            )
        return self.slots[self.index]

    def usable(self) -> list[KeySlot]:
        return [s for s in self.slots if s.usable]

    # ---- failure handling ------------------------------------------------
    def mark_exhausted(self, reason: str = "quota") -> None:
        slot = self.current
        slot.exhausted_at = datetime.now(timezone.utc)
        slot.failures += 1

    def mark_rejected(self) -> None:
        slot = self.current
        slot.rejected_at = datetime.now(timezone.utc)
        slot.failures += 1

    def rotate(self) -> KeySlot:
        """Advance to the next usable key, or raise if there is none left."""
        if self.pinned:
            raise NoKeysAvailable(
                f"key {self.current.label} is {self.current.state} and rotation is "
                "pinned to it. Choose another key, or clear the pin to rotate."
            )
        for offset in range(1, len(self.slots) + 1):
            candidate = (self.index + offset) % len(self.slots)
            if self.slots[candidate].usable:
                self.index = candidate
                return self.slots[candidate]
        raise NoKeysAvailable(
            "every configured key is exhausted or rejected: "
            + ", ".join(f"{s.label}={s.state}" for s in self.slots)
        )

    def note_call(self) -> None:
        if self.slots:
            self.current.calls += 1

    # ---- reporting -------------------------------------------------------
    def __len__(self) -> int:
        return len(self.slots)

    def __iter__(self) -> Iterator[KeySlot]:
        return iter(self.slots)

    def as_dict(self) -> dict:
        return {
            "count": len(self.slots),
            "active": self.slots[self.index].label if self.slots else None,
            "pinned": self.pinned,
            "usable": len(self.usable()),
            "keys": [s.as_dict() for s in self.slots],
        }
