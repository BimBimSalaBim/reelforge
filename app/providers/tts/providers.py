"""Concrete TTS engines.

All of them synthesize one phrase per call; `joiner.join` assembles the track.
"""
from __future__ import annotations

#: Seconds a reachability probe may take. These run when a form opens, so a
#: dead endpoint must fail fast rather than hold the page.
PROBE_TIMEOUT = 4.0

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import secret
from app.providers.keyring import KeyRing, NoKeysAvailable
from app.providers.tts.base import TTSError, TTSProvider, UploadRequired


class UploadProvider(TTSProvider):
    """Not an engine -- the marker that a human supplies the audio."""

    name = "upload"

    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        raise UploadRequired(
            "the audio provider is 'upload': supply a narration file for this job"
        )

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "reachable": True,
                "note": "audio is supplied by the user"}


class ElevenLabsProvider(TTSProvider):
    """ElevenLabs over its REST API.

    Uses HTTP directly rather than the `elevenlabs` SDK so the adapter has the
    same shape, timeout handling and error surface as every other provider here,
    and so the image needs one less dependency. The request is the documented
    `text_to_speech.convert` call: voice_id in the path, model_id and
    voice_settings in the body, output_format as a query parameter.

    Credits are metered per character, so `max_characters_per_job` refuses an
    obviously-overlong job before spending anything, and `characters_used`
    tracks what a run actually cost.
    """

    name = "elevenlabs"
    output_mime = "audio/mpeg"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url", "https://api.elevenlabs.io/v1")).rstrip("/")
        self.voice_id = settings.get("voice_id") or ""
        self.voice = self.voice_id
        self.model = settings.get("model", "eleven_multilingual_v2")
        self.output_format = settings.get("output_format", "mp3_44100_128")
        self.max_characters = int(settings.get("max_characters_per_job", 4000))
        self.characters_used = 0

        env_names = settings.get("api_key_envs") or [
            settings.get("api_key_env", "ELEVENLABS_API_KEY")
        ]
        self.keys = KeyRing.from_env(env_names, active=settings.get("active_key"))
        if not len(self.keys):
            raise TTSError(
                f"no ElevenLabs key found. Set one of {env_names} in .env "
                "(a variable may hold several keys separated by commas). Keys are "
                "read from the environment, never from config.yaml."
            )
        self.rotations: list[dict] = []
        self._client = httpx.Client(base_url=self.base_url, timeout=180.0)

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.keys.current.value}

    def select_key(self, which: str | int) -> dict[str, Any]:
        """Pin a specific key. Rotation stops until `use_any_key()` is called."""
        slot = self.keys.select(which)
        return {"active": slot.label, "pinned": True}

    def use_any_key(self) -> dict[str, Any]:
        """Release a manual pin and resume automatic rotation."""
        return self.keys.auto().as_dict()

    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        """Synthesize one phrase, rotating keys if this one is finished.

        A narration is a dozen calls and an allowance can run out between two of
        them, so rotation happens here rather than at job start. Each attempt is
        made once per usable key; a 401 or 429 retires that key for the rest of
        the run rather than being retried.
        """
        if self.characters_used + len(text) > self.max_characters:
            raise TTSError(
                f"this job would use {self.characters_used + len(text)} characters, over "
                f"the {self.max_characters} limit set by tts.elevenlabs."
                "max_characters_per_job. Raise it deliberately if that is intended."
            )

        body = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {
                "stability": float(self.settings.get("stability", 0.5)),
                "similarity_boost": float(self.settings.get("similarity_boost", 0.75)),
                "style": float(self.settings.get("style", 0.0)),
                "use_speaker_boost": bool(self.settings.get("use_speaker_boost", True)),
            },
        }

        last_error = ""
        for _ in range(max(1, len(self.keys))):
            slot = self.keys.current
            self.keys.note_call()
            response = self._client.post(
                f"/text-to-speech/{self.voice_id}",
                params={"output_format": self.output_format},
                headers=self._headers(),
                json=body,
            )
            if response.status_code < 400:
                self.characters_used += len(text)
                return response.content

            if response.status_code == 401:
                self.keys.mark_rejected()
                last_error = f"key {slot.label} was rejected (401)"
            elif response.status_code in (429, 402):
                self.keys.mark_exhausted()
                last_error = f"key {slot.label} is out of credits ({response.status_code})"
            else:
                raise TTSError(f"elevenlabs {response.status_code}: {response.text[:300]}")

            try:
                nxt = self.keys.rotate()
            except NoKeysAvailable as exc:
                raise TTSError(f"{last_error}. {exc}") from None
            self.rotations.append({"from": slot.label, "to": nxt.label,
                                   "reason": last_error})

        raise TTSError(last_error or "elevenlabs request failed")

    def estimate(self, texts: list[str]) -> dict[str, Any]:
        """What a job would cost, before spending anything."""
        total = sum(len(t) for t in texts)
        return {"characters": total, "phrases": len(texts),
                "limit": self.max_characters, "within_limit": total <= self.max_characters,
                "keys_available": len(self.keys.usable())}

    def health(self) -> dict[str, Any]:
        """Reads subscription and voice list only -- costs no credits."""
        out: dict[str, Any] = {"provider": self.name, "reachable": False,
                               "voice_id": self.voice_id, "model": self.model,
                               "output_format": self.output_format,
                               "keys": self.keys.as_dict()}
        try:
            response = self._client.get("/voices", timeout=PROBE_TIMEOUT, headers=self._headers())
            response.raise_for_status()
            voices = {v["voice_id"]: v.get("name") for v in response.json().get("voices", [])}
            out.update({"reachable": True,
                        "voice_present": self.voice_id in voices,
                        "voice_name": voices.get(self.voice_id),
                        "voices": [{"id": k, "name": v} for k, v in list(voices.items())[:60]]})
        except Exception as exc:
            out["error"] = str(exc)[:200]

        # per-key credit report, so the UI can show which key to switch to.
        # Reading a subscription costs no characters.
        balances = []
        for position, slot in enumerate(self.keys):
            entry = {"label": slot.label, "state": slot.state, "key": slot.masked()}
            try:
                sub = self._client.get(
                    "/user/subscription", timeout=PROBE_TIMEOUT,
                    headers={"xi-api-key": slot.value},
                ).json()
                used, limit = sub.get("character_count"), sub.get("character_limit")
                entry.update({
                    "used": used, "limit": limit, "tier": sub.get("tier"),
                    "remaining": (limit - used) if None not in (used, limit) else None,
                })
            except Exception as exc:
                entry["error"] = str(exc)[:120]
            balances.append(entry)
        out["key_balances"] = balances
        out["total_remaining"] = sum(
            b.get("remaining") or 0 for b in balances if isinstance(b.get("remaining"), int)
        )
        return out


class OpenAITTSProvider(TTSProvider):
    name = "openai"
    output_mime = "audio/mpeg"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.model = settings.get("model", "gpt-4o-mini-tts")
        self.voice = settings.get("voice", "onyx")
        key = secret(settings.get("api_key_env", "OPENAI_API_KEY"))
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=180.0)

    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        payload: dict[str, Any] = {
            "model": self.model, "voice": self.voice, "input": text,
            "response_format": "mp3",
        }
        # The measured, level delivery the existing scripts ask the narrator for.
        if self.settings.get("instructions"):
            payload["instructions"] = self.settings["instructions"]
        response = self._client.post("/audio/speech", json=payload)
        if response.status_code >= 400:
            raise TTSError(f"openai tts {response.status_code}: {response.text[:300]}")
        return response.content

    def health(self) -> dict[str, Any]:
        try:
            self._client.get("/models", timeout=PROBE_TIMEOUT).raise_for_status()
            return {"provider": self.name, "reachable": True,
                    "model": self.model, "voice": self.voice}
        except Exception as exc:
            return {"provider": self.name, "reachable": False, "error": str(exc)[:200]}


class LocalHTTPProvider(TTSProvider):
    """A self-hosted engine behind HTTP -- Kokoro, Piper, or anything that
    accepts `{text, voice}` and returns audio bytes.

    Kokoro's common container exposes an OpenAI-shaped `/v1/audio/speech`, so
    that path is tried first and a plainer `/tts` second.
    """

    name = "local"
    output_mime = "audio/wav"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url", "http://tts:8080")).rstrip("/")
        self.engine = settings.get("engine", "kokoro")
        self.voice = settings.get("voice", "af_heart")
        self._client = httpx.Client(base_url=self.base_url, timeout=300.0)

    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        attempts = [
            ("/v1/audio/speech",
             {"model": self.engine, "voice": self.voice, "input": text,
              "response_format": "wav"}),
            ("/tts", {"text": text, "voice": self.voice}),
        ]
        errors = []
        for path, payload in attempts:
            try:
                response = self._client.post(path, json=payload)
            except httpx.HTTPError as exc:
                errors.append(f"{path}: {exc}")
                continue
            if response.status_code < 400 and response.content:
                return response.content
            errors.append(f"{path}: HTTP {response.status_code} {response.text[:160]}")
        raise TTSError(f"local tts at {self.base_url} failed:\n" + "\n".join(errors))

    def health(self) -> dict[str, Any]:
        for path in ("/health", "/v1/models", "/"):
            try:
                response = self._client.get(path, timeout=PROBE_TIMEOUT)
                if response.status_code < 500:
                    return {"provider": self.name, "reachable": True,
                            "base_url": self.base_url, "engine": self.engine,
                            "voice": self.voice, "probe": path}
            except httpx.HTTPError:
                continue
        return {"provider": self.name, "reachable": False, "base_url": self.base_url}


class SayProvider(TTSProvider):
    """macOS `say`. Not for production -- it exists so the whole pipeline can be
    exercised on a laptop with no API key, no GPU and no container."""

    name = "say"
    output_mime = "audio/aiff"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.voice = settings.get("voice", "Daniel")
        self.rate = int(settings.get("rate", 170))
        if not shutil.which("say"):
            raise TTSError("`say` is only available on macOS")

    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "phrase.aiff"
            cmd = ["say", "-o", str(out), "-r", str(self.rate)]
            if self.voice:
                cmd += ["-v", self.voice]
            proc = subprocess.run(cmd + [text], capture_output=True, check=False)
            if proc.returncode != 0 or not out.exists():
                raise TTSError(f"say failed: {proc.stderr.decode()[:200]}")
            return out.read_bytes()

    def health(self) -> dict[str, Any]:
        return {"provider": self.name, "reachable": bool(shutil.which("say")),
                "voice": self.voice, "note": "development only"}
