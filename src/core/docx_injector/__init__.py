"""
src/core/docx_injector/__init__.py
Clean Architecture - Core Layer
"""

from .docx_injector_service import inject_signature_to_docx, PlaceholderNotFoundError

__all__ = ["inject_signature_to_docx", "PlaceholderNotFoundError"]
