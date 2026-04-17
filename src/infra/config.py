# core/config.py
# Konfigurasi global Word Signer
# Edit file ini untuk menyesuaikan behavior per institusi / deployment

import platform
import os


# ── LibreOffice ───────────────────────────────────────────────

def get_libreoffice_path() -> str:
    system = platform.system()
    if system == "Windows":
        return r"C:\Program Files\LibreOffice\program\soffice.exe"
    elif system == "Darwin":  # macOS
        return "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    else:  # Linux
        return "/usr/bin/libreoffice"

LIBREOFFICE_PATH = get_libreoffice_path()


# ── Detection ─────────────────────────────────────────────────

# Minimum confidence score untuk zona TTD dianggap valid (0.0 – 1.0)
CONFIDENCE_THRESHOLD = 0.4

# Minimal panjang karakter untuk dianggap garis putus-putus (--- atau ___)
DASH_LINE_MIN = 5

# Jumlah halaman terakhir yang di-scan untuk zona TTD
# Naikkan jika TTD tersebar di banyak halaman, turunkan untuk lebih ketat
LAST_PAGES_SCAN = 2

# Baris yang diabaikan saat parsing teks cell
# Kosongkan list ini untuk institusi non-BNI
IGNORED_LINES = [
    "pt. bank negara indonesia (persero) tbk.",
    "pt. bank negara indonesia (persero)",
    "tbk.",
    "tbk",
]


# ── Signature ─────────────────────────────────────────────────

# Format file tanda tangan yang didukung
ALLOWED_SIGNATURE_FORMATS = ["svg", "png", "jpg", "jpeg"]

# Lebar default tanda tangan dalam inci (dipakai GUI)
SIGNATURE_WIDTH_INCHES = 1.5


# ── App ───────────────────────────────────────────────────────

# Buka PDF otomatis setelah selesai (GUI only)
AUTO_OPEN_PDF = True

# Batas konversi LibreOffice yang boleh berjalan bersamaan.
# Turunkan jika RAM server terbatas, naikkan jika server berspesifikasi tinggi.
MAX_CONVERSIONS: int = int(os.getenv("MAX_CONVERSIONS", "3"))