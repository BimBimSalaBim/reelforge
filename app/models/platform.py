"""Per-platform post metadata.

One video serves every platform; only the words change. `hashtags` lives once on
`ReelContent` and is referenced here, which fixes the current hand-duplication
between `captions.txt` and `<name>-reel-notes.md`.

Each model carries its own platform rules as validators, so a generation that
breaks a limit is caught before a human ever sees it and is fed back to the LLM.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Platform limits, deliberately conservative where a platform is vague.
IG_HOOK_VISIBLE = 125       # what shows before Instagram's "... more"
IG_CAPTION_MAX = 2200
YT_TITLE_MAX = 100
YT_DESC_MAX = 5000
FB_CAPTION_MAX = 2000
LI_POST_MAX = 3000
LI_HOOK_VISIBLE = 210       # LinkedIn truncates later than Instagram


def _visible_len(text: str) -> int:
    return len(text.strip())


class PlatformPost(BaseModel):
    platform: str
    hashtags: list[str] = Field(default_factory=list)

    def render_text(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


# --------------------------------------------------------- instagram ------
class InstagramPost(PlatformPost):
    platform: Literal["instagram"] = "instagram"
    hook: str
    body: list[str] = Field(min_length=1, max_length=5)
    stats_line: str
    save_prompt: str
    question: str
    alt_text: str = Field(default="", max_length=1000)
    pinned_comment: str = ""

    @field_validator("hook")
    @classmethod
    def _hook_fits(cls, v: str) -> str:
        """Trim to the fold rather than rejecting the whole bundle.

        Instagram hides everything past 125 characters behind "... more"
        regardless, so a 131-character hook is not a judgment call the model
        needs to make again -- it is six characters, and losing a whole
        generation over them is the same waste as re-asking for a forgotten
        `SFX` line. Trimming lands on a word boundary so it reads as written.

        A hook far over the limit is a different thing: it means the model
        wrote a paragraph where a line was asked for, and that does go back.
        """
        text = " ".join(v.split())
        if _visible_len(text) <= IG_HOOK_VISIBLE:
            return text
        if _visible_len(text) > IG_HOOK_VISIBLE * 1.6:
            raise ValueError(
                f"Instagram hook is {_visible_len(text)} chars; it must be <= "
                f"{IG_HOOK_VISIBLE} so it is fully visible before the '... more' "
                "fold. Write one line, not a paragraph."
            )
        from app.text import trim_to

        return trim_to(text, IG_HOOK_VISIBLE)

    @field_validator("hashtags")
    @classmethod
    def _five_or_pending(cls, v: list[str]) -> list[str]:
        """Empty means "not filled in yet".

        Hashtags live once on the content and are applied by
        `PlatformBundle.apply_hashtags`, so the generation prompt asks for them
        to be left out. Demanding five at construction made that impossible to
        satisfy. `render_text` enforces the count once they have been applied.
        """
        if v and len(v) != 5:
            raise ValueError(f"Instagram takes exactly 5 hashtags, got {len(v)}")
        return v

    def render_text(self) -> str:
        if len(self.hashtags) != 5:
            raise ValueError(
                f"Instagram needs exactly 5 hashtags before rendering, has "
                f"{len(self.hashtags)}. They come from ReelContent via "
                "PlatformBundle.apply_hashtags()."
            )
        parts = [self.hook, "", *self._spaced(self.body), self.stats_line, "",
                 self.save_prompt, self.question, "", " ".join(self.hashtags)]
        text = "\n".join(parts).strip() + "\n"
        if len(text) > IG_CAPTION_MAX:
            raise ValueError(f"Instagram caption is {len(text)} chars, max {IG_CAPTION_MAX}")
        return text

    @staticmethod
    def _spaced(paragraphs: list[str]) -> list[str]:
        out: list[str] = []
        for para in paragraphs:
            out.extend([para, ""])
        return out


# ----------------------------------------------------------- youtube ------
class YouTubePost(PlatformPost):
    platform: Literal["youtube"] = "youtube"
    title: str
    description_body: list[str] = Field(min_length=1)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("title")
    @classmethod
    def _title_rules(cls, v: str) -> str:
        v = v.strip()
        if not v.endswith("#shorts"):
            v = f"{v} #shorts"
        if len(v) > YT_TITLE_MAX:
            raise ValueError(
                f"YouTube title is {len(v)} chars including ' #shorts'; max {YT_TITLE_MAX}"
            )
        return v

    def render_description(self) -> str:
        parts = list(self.description_body)
        if self.links:
            parts.append("\n".join(self.links))
        parts.append(" ".join(self.hashtags))
        text = "\n\n".join(p.strip() for p in parts if p.strip()) + "\n"
        if len(text) > YT_DESC_MAX:
            raise ValueError(f"YouTube description is {len(text)} chars, max {YT_DESC_MAX}")
        return text

    def render_text(self) -> str:
        return f"{self.title}\n\n{self.render_description()}"


# ---------------------------------------------------------- facebook ------
class FacebookPost(PlatformPost):
    platform: Literal["facebook"] = "facebook"
    hook: str
    body: list[str] = Field(min_length=1, max_length=4)
    call_to_action: str

    @field_validator("hashtags")
    @classmethod
    def _at_most_three(cls, v: list[str]) -> list[str]:
        if len(v) > 3:
            raise ValueError(f"Facebook takes at most 3 hashtags, got {len(v)}")
        return v

    def render_text(self) -> str:
        parts = [self.hook, "", *self.body, "", self.call_to_action]
        if self.hashtags:
            parts += ["", " ".join(self.hashtags)]
        text = "\n".join(parts).strip() + "\n"
        if len(text) > FB_CAPTION_MAX:
            raise ValueError(f"Facebook caption is {len(text)} chars, max {FB_CAPTION_MAX}")
        return text


# ---------------------------------------------------------- linkedin ------
class LinkedInPost(PlatformPost):
    platform: Literal["linkedin"] = "linkedin"
    hook: str
    body: list[str] = Field(min_length=2, max_length=6)
    takeaway: str
    question: str
    first_comment: str = ""

    @field_validator("hook")
    @classmethod
    def _hook_fits(cls, v: str) -> str:
        if _visible_len(v) > LI_HOOK_VISIBLE:
            raise ValueError(
                f"LinkedIn hook is {_visible_len(v)} chars; keep it <= {LI_HOOK_VISIBLE} "
                "so it survives the 'see more' fold"
            )
        return v.strip()

    @field_validator("hashtags")
    @classmethod
    def _at_most_three(cls, v: list[str]) -> list[str]:
        if len(v) > 3:
            raise ValueError(f"LinkedIn takes at most 3 hashtags, got {len(v)}")
        return v

    @model_validator(mode="after")
    def _register(self) -> "LinkedInPost":
        # LinkedIn's feed renders shell prompts badly and the register is wrong
        # for the audience; the install command belongs in the first comment.
        for para in self.body:
            if re.search(r"^\s*[$>›]\s", para, flags=re.M):
                raise ValueError(
                    "LinkedIn body must not contain a shell prompt line; "
                    "put the install command in first_comment instead"
                )
        return self

    def render_text(self) -> str:
        parts = [self.hook, "", *self.body, "", self.takeaway, "", self.question]
        if self.hashtags:
            parts += ["", " ".join(self.hashtags)]
        text = "\n".join(parts).strip() + "\n"
        if len(text) > LI_POST_MAX:
            raise ValueError(f"LinkedIn post is {len(text)} chars, max {LI_POST_MAX}")
        return text


class PlatformBundle(BaseModel):
    instagram: InstagramPost
    youtube: YouTubePost
    facebook: FacebookPost
    linkedin: LinkedInPost

    def all(self) -> list[PlatformPost]:
        return [self.instagram, self.youtube, self.facebook, self.linkedin]

    def apply_hashtags(self, five: list[str]) -> "PlatformBundle":
        """Single source of truth: Instagram and YouTube take all five,
        Facebook and LinkedIn take the three broadest."""
        self.instagram.hashtags = list(five)
        self.youtube.hashtags = list(five)
        self.facebook.hashtags = list(five[:3])
        self.linkedin.hashtags = list(five[:3])
        return self
