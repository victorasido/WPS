# logger_service.py
# Log history operasi TTD — format human-readable untuk orang awam

import os
from datetime import datetime

APP_DIR  = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "WordSigner")
LOG_FILE = os.path.join(APP_DIR, "history.log")

# Batas max baris log sebelum di-rotate (biar file tidak membengkak)
MAX_LINES = 500


def log_success(input_path: str, output_path: str, zone_count: int):
    """Log operasi berhasil."""
    nama_input  = os.path.basename(input_path)
    nama_output = os.path.basename(output_path)
    _log(
        status="✓ BERHASIL",
        detail=(
            f"Dokumen  : {nama_input}\n"
            f"{'':>20}Output   : {nama_output}\n"
            f"{'':>20}TTD      : {zone_count} zona ditandatangani"
        )
    )


def log_error(input_path: str, error: str):
    """Log operasi gagal."""
    nama_input = os.path.basename(input_path) if input_path else "(tidak diketahui)"
    # Sederhanakan pesan error untuk orang awam
    pesan = _simplify_error(error)
    _log(
        status="✗ GAGAL",
        detail=(
            f"Dokumen  : {nama_input}\n"
            f"{'':>20}Penyebab : {pesan}"
        )
    )


def log_info(message: str):
    """Log pesan informasi umum."""
    _log(status="ℹ INFO", detail=message)


# ── Internal ─────────────────────────────────────────────────

def _log(status: str, detail: str):
    os.makedirs(APP_DIR, exist_ok=True)
    _rotate_if_needed()

    ts   = datetime.now().strftime("%d %b %Y, %H:%M")
    line = f"[{ts}]  {status}\n{'':>20}{detail}\n"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _simplify_error(error: str) -> str:
    """Konversi pesan error teknis jadi bahasa yang lebih mudah dipahami."""
    err = str(error).lower()

    if "zona ttd tidak ditemukan" in err or "not found" in err:
        return "Zona tanda tangan tidak ditemukan di dokumen ini."
    if "libreoffice" in err:
        return "LibreOffice tidak dapat mengkonversi dokumen. Pastikan LibreOffice terinstall."
    if "permission" in err or "access" in err:
        return "Tidak bisa mengakses file. Pastikan file tidak sedang dibuka di aplikasi lain."
    if "format" in err or "tidak didukung" in err:
        return "Format file tanda tangan tidak didukung. Gunakan PNG, JPG, atau SVG."
    if "corrupt" in err or "invalid" in err:
        return "File dokumen rusak atau tidak valid."
    if "memory" in err or "out of" in err:
        return "Memori tidak cukup untuk memproses dokumen ini."

    # Fallback: potong pesan error panjang
    brief = str(error)
    return brief[:100] + ("..." if len(brief) > 100 else "")


def _rotate_if_needed():
    """Hapus baris lama jika log terlalu panjang."""
    if not os.path.exists(LOG_FILE):
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            # Simpan hanya setengah terakhir
            keep = lines[len(lines) // 2:]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"[Log dipangkas otomatis pada {datetime.now().strftime('%d %b %Y')}]\n\n")
                f.writelines(keep)
    except Exception:
        pass