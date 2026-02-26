#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "defusedxml",
#     "lxml",
# ]
# ///

"""
Validation modules for Word document processing.
"""

from .base import BaseSchemaValidator
from .docx import DOCXSchemaValidator
from .pptx import PPTXSchemaValidator
from .redlining import RedliningValidator

__all__ = [
    "BaseSchemaValidator",
    "DOCXSchemaValidator",
    "PPTXSchemaValidator",
    "RedliningValidator",
]
