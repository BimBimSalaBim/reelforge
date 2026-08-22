"""The TTS interface.

Every engine here speaks *one phrase at a time*. That is the whole trick.

`video/align.py` splits audio on silence and refuses to build unless the number
of detected voiced segments equals the number of phrase lines. Handing a whole
paragraph to a TTS engine and hoping it pauses in the right places reproduces
the manual reconciliation the current process does by hand. Synthesizing each
phrase separately and joining them with a known amount of real silence makes the
segment count equal the phrase count by construction.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.models.content import Phrase


class TTSError(RuntimeError):
    pass


class UploadRequired(TTSError):
    """The configured provider is `upload`; a human has to supply the file."""


@dataclass
class SpokenPhrase:
    index: int
    text: str
    audio: bytes
    mime: str
    seconds: float | None = None


@dataclass
class TTSResult:
    phrases: list[SpokenPhrase]
    provider: str
    voice: str
    meta: dict[str, Any] = field(default_factory=dict)


class TTSProvider(abc.ABC):
    name = "base"
    #: format the engine returns; the joiner normalises everything to WAV anyway
    output_mime = "audio/wav"

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.voice: str = str(settings.get("voice") or settings.get("voice_id") or "")

    @abc.abstractmethod
    def speak(self, text: str, *, hints: dict[str, int] | None = None) -> bytes:
        """Synthesize one phrase and return encoded audio bytes."""

    @abc.abstractmethod
    def health(self) -> dict[str, Any]:
        ...

    def speak_all(
        self, phrases: list[Phrase], *, hints: dict[str, int] | None = None,
        progress=None,
    ) -> TTSResult:
        spoken: list[SpokenPhrase] = []
        for index, phrase in enumerate(phrases):
            audio = self.speak(phrase.text, hints=hints)
            spoken.append(SpokenPhrase(index=index, text=phrase.text,
                                       audio=audio, mime=self.output_mime))
            if progress:
                progress((index + 1) / len(phrases), f"spoke phrase {index + 1}/{len(phrases)}")
        return TTSResult(phrases=spoken, provider=self.name, voice=self.voice)
