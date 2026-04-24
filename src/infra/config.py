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


# ── Runtime Environment ───────────────────────────────────────────────────────

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()


def _get_int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _get_float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


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
# Production default dibuat lebih konservatif agar VPS kecil tidak mudah timeout/OOM.
MAX_CONVERSIONS = _get_int_env(
    "MAX_CONVERSIONS",
    1 if APP_ENV == "production" else 3,
)

# Batas waktu subprocess LibreOffice agar proses tidak menggantung terlalu lama.
LIBREOFFICE_TIMEOUT = _get_int_env(
    "LIBREOFFICE_TIMEOUT",
    180 if APP_ENV == "production" else 300,
)

# Timeout koneksi Telegram API. Upload/download file besar di server butuh headroom
# lebih besar dibanding lokal.
TELEGRAM_CONNECT_TIMEOUT = _get_float_env("TELEGRAM_CONNECT_TIMEOUT", 30.0)
TELEGRAM_READ_TIMEOUT = _get_float_env("TELEGRAM_READ_TIMEOUT", 180.0)
TELEGRAM_WRITE_TIMEOUT = _get_float_env("TELEGRAM_WRITE_TIMEOUT", 180.0)
TELEGRAM_POOL_TIMEOUT = _get_float_env("TELEGRAM_POOL_TIMEOUT", 30.0)
