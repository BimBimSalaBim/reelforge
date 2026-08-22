"""Prompt construction. Kept apart from the stages so prompts can be reviewed,
diffed and versioned as the artefacts they are."""
from app.prompts.content import build_content_prompt, condense_readme
from app.prompts.platform import build_platform_prompt

__all__ = ["build_content_prompt", "condense_readme", "build_platform_prompt"]
