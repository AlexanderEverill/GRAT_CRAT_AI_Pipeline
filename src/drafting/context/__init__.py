"""Context assembly package for drafting stage."""

from .client_context import format_client_context_block
from .numeric_binder import bind_numeric_values
from .section_context import GENERAL_BUCKET_ID, build_section_context

__all__ = [
	"GENERAL_BUCKET_ID",
	"bind_numeric_values",
	"build_section_context",
	"format_client_context_block",
]
