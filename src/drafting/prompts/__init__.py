"""Prompt templates package for drafting stage."""

from .citation_instructions import citation_instruction_block
from .section_prompt import DEFAULT_TOKEN_BUDGET, section_draft_prompt_builder
from .system_prompt import SYSTEM_PROMPT, system_prompt_template

__all__ = [
	"citation_instruction_block",
	"DEFAULT_TOKEN_BUDGET",
	"SYSTEM_PROMPT",
	"section_draft_prompt_builder",
	"system_prompt_template",
]
