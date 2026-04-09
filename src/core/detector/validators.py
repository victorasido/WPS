"""
services/detector/validators.py
Semantic validation untuk menentukan apakah teks merupakan
zona TTD yang valid atau sekedar label/key-value field.
"""

import re
from typing import Protocol, runtime_checkable


# ── Semantic Validation (Protocol / Duck Typing) ─────────────

@runtime_checkable
class SemanticValidator(Protocol):
    """Duck Typing Protocol: setiap kelas yang memiliki is_valid() bisa dipakai."""
    def is_valid(self, text: str) -> bool: ...


class DefaultSemanticValidator:
    """
    Implementasi default SemanticValidator.
    Menolak teks yang merupakan label key-value (bukan area TTD).
    Contoh yang ditolak: "Dibuat oleh:", "Disetujui: Ya", "by: Farino"
    """
    _REJECT_PATTERNS = [
        re.compile(r":\s*$"),          # diakhiri titik dua → tetap label field (kosong)
        re.compile(r"by\s*:", re.I),   # "by:" → indikasi log/metadata
        # re.compile(r"\w+\s*:\s*\S"), # Terlalu agresif, memblokir "Jabatan: Manager"
    ]

    def is_valid(self, text: str) -> bool:
        clean = text.strip()
        if not clean:
            return False
        return not any(p.search(clean) for p in self._REJECT_PATTERNS)


# Singleton validator default — bisa di-override saat testing
DEFAULT_VALIDATOR: SemanticValidator = DefaultSemanticValidator()
