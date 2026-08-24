"""Fish-Speech (OpenAudio) behind its Gradio app.

The app exposes one endpoint, `/partial`: text in, a wav path out, with an
optional reference voice given as an audio file plus its transcript. Reached
through `gradio_client`, which does the upload and the queue handshake.

The one thing worth knowing: the narration is synthesized phrase by phrase,
and without a reference the model is free to pick a different timbre each
call. So a reference is always used. Either the profile names one
(`reference_audio`, a wav of the voice you want, with `reference_text` its
transcript), or the adapter makes its own: one seeded calibration sentence,
generated once and kept under `data/tts/fish/`, then fed back as the
reference for every phrase of every reel. The same seed is the same voice
tomorrow.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.providers.tts.base import TTSError, TTSProvider

PROBE_TIMEOUT = 6.0


def _plain(text: str) -> str:
    """The app reports errors as HTML; the log wants the sentence inside."""
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
#: Spoken once to fix the voice when no reference is configured. Long enough
#: for the model to settle into a timbre, short enough to be cheap.
CALIBRATION = ("This is the narration voice. It stays level and clear, and it reads "
               "every line the same way, from the first word to the last.")


class FishSpeechProvider(TTSProvider):
    name = "fish"
    output_mime = "audio/wav"

    def __init__(self, settings: dict[str, Any]):
        super().__init__(settings)
        self.base_url = str(settings.get("base_url") or "http://localhost:7860").rstrip("/") + "/"
        self.api_name = str(settings.get("api_name") or "/partial")
        self.reference_id = str(settings.get("reference_id") or "")
        self.reference_audio = str(settings.get("reference_audio") or "")
        self.reference_text = str(settings.get("reference_text") or "")
        self.temperature = float(settings.get("temperature", 0.8))
        self.top_p = float(settings.get("top_p", 0.8))
        self.repetition_penalty = float(settings.get("repetition_penalty", 1.1))
        self.seed = int(settings.get("seed", 1))
        self.chunk_length = int(settings.get("chunk_length", 300))
        self.voice = self.reference_id or (Path(self.reference_audio).stem if self.reference_audio
                                           else f"self-reference seed {self.seed}")
        self._client = None
        self._reference: tuple[str | None, str] | None = None

    # ---------------------------------------------------------- client ---
    def client(self):
        if self._client is None:
            try:
                from gradio_client import Client
            except ImportError as exc:
                raise TTSError("the fish adapter needs the gradio_client package: "
                               "pip install gradio_client") from exc
            try:
                self._client = Client(self.base_url, verbose=False, download_files=True)
            except Exception as exc:
                raise TTSError(f"Fish-Speech at {self.base_url} unreachable: {str(exc)[:200]}") from exc
        return self._client

    def _predict(self, text: str, reference_audio: str | None, reference_text: str,
                 seed: int) -> Path:
        from gradio_client import handle_file

        try:
            result = self.client().predict(
                text=text, reference_id=self.reference_id,
                reference_audio=handle_file(reference_audio) if reference_audio else None,
                reference_text=reference_text, max_new_tokens=0,
                chunk_length=self.chunk_length, top_p=self.top_p,
                repetition_penalty=self.repetition_penalty, temperature=self.temperature,
                seed=seed, use_memory_cache="on", api_name=self.api_name,
            )
        except Exception as exc:
            raise TTSError(f"Fish-Speech failed: {str(exc)[:300]}") from exc
        audio, error = (result[0], result[1]) if isinstance(result, (list, tuple)) else (result, None)
        if error:
            raise TTSError(f"Fish-Speech reported: {_plain(str(error))[:300]}")
        if not audio or not Path(str(audio)).exists():
            raise TTSError("Fish-Speech returned no audio file")
        return Path(str(audio))

    # ------------------------------------------------------- reference ---
    def reference(self) -> tuple[str | None, str]:
        """(audio path, transcript) used for every phrase."""
        if self._reference is not None:
            return self._reference
        if self.reference_audio:
            path = Path(self.reference_audio).expanduser()
            if not path.exists():
                raise TTSError(f"reference_audio not found: {path}")
            self._reference = (str(path), self.reference_text)
        elif self.reference_id:
            # a voice the server already knows by id; nothing to upload
            self._reference = (None, "")
        else:
            self._reference = (str(self._calibration()), CALIBRATION)
        return self._reference

    def _calibration(self) -> Path:
        from app.config import get_config

        key = hashlib.sha1(f"{self.base_url}|{self.seed}|{CALIBRATION}".encode()).hexdigest()[:10]
        target = get_config().paths.data / "tts" / "fish" / f"reference-{self.seed}-{key}.wav"
        if target.exists() and target.stat().st_size > 1000:
            return target
        produced = self._predict(CALIBRATION, None, "", self.seed)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(produced.read_bytes())
        return target

    # ----------------------------------------------------------- speak ---
    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        audio, transcript = self.reference()
        try:
            return self._predict(text, audio, transcript, self.seed).read_bytes()
        except TTSError as exc:
            # "CUDA out of memory" is usually another model holding the card
            # for a moment longer -- the visuals stage has just been told to
            # let go. One short retry covers the handover.
            if "out of memory" not in str(exc).lower():
                raise
            import time

            time.sleep(4.0)
            return self._predict(text, audio, transcript, self.seed).read_bytes()

    def health(self) -> dict[str, Any]:
        import httpx

        out: dict[str, Any] = {"provider": self.name, "base_url": self.base_url,
                               "voice": self.voice, "api_name": self.api_name}
        try:
            response = httpx.get(self.base_url + "config", timeout=PROBE_TIMEOUT)
            response.raise_for_status()
            config = response.json()
        except Exception as exc:
            out |= {"reachable": False, "error": f"{self.base_url} unreachable: {str(exc)[:160]}"}
            return out
        out["reachable"] = True
        names = {d.get("api_name") for d in config.get("dependencies", []) if isinstance(d, dict)}
        wanted = self.api_name.lstrip("/")
        if names and wanted not in names:
            out["error"] = (f"the app has no {self.api_name} endpoint; it offers "
                            + ", ".join("/" + n for n in sorted(n for n in names if n)))
        if self.reference_audio and not Path(self.reference_audio).expanduser().exists():
            out["error"] = f"reference_audio not found: {self.reference_audio}"
        out["note"] = ("voice cloned from " + self.reference_audio if self.reference_audio
                       else (f"server voice {self.reference_id}" if self.reference_id
                             else f"self-referenced calibration voice, seed {self.seed}"))
        return out
