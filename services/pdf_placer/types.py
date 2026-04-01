# services/pdf_placer/types.py
# Shared data types untuk pdf_placer module.

from __future__ import annotations
from dataclasses import dataclass
import fitz


@dataclass
class SignaturePlacement:
    """Represents one resolved signature placement in the PDF."""
    page:       fitz.Page
    rect:       fitz.Rect
    method:     str    # e.g. "line_based", "table_based", "free_space", "legacy_..."
    confidence: float  # 0.0–1.0
