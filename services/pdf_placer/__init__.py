# services/pdf_placer/__init__.py
# Public API for the pdf_placer module.

from .signature_placer import place_all_signatures
from .types import SignaturePlacement

__all__ = ["place_all_signatures", "SignaturePlacement"]
