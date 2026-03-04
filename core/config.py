import os
import platform

# LibreOffice path per OS
def get_libreoffice_path() -> str:
    system = platform.system()
    if system == "Windows":
        return r"C:\Program Files\LibreOffice\program\soffice.exe"
    elif system == "Darwin":  # macOS
        return "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    else:  # Linux
        return "libreoffice"

LIBREOFFICE_PATH = get_libreoffice_path()

# Format TTD yang diperbolehkan
ALLOWED_SIGNATURE_FORMATS = ["svg", "png", "jpg", "jpeg"]

# Grid scan setting
GRID_COLS = 2
GRID_ROWS = 3

# Confidence threshold untuk deteksi zona TTD
CONFIDENCE_THRESHOLD = 0.4

# Lebar default TTD dalam inci
SIGNATURE_WIDTH_INCHES = 1.5

# Auto-buka PDF setelah konversi
AUTO_OPEN_PDF = True

# Jumlah halaman terakhir yang di-scan untuk deteksi zona TTD
# Naikan jika TTD tersebar di banyak halaman, turunkan untuk lebih ketat
LAST_PAGES_SCAN = 2