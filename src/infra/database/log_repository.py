import os
from datetime import datetime

class LogRepository:
    def __init__(self):
        data_dir = os.getenv("DATA_DIR")
        if data_dir:
            self.app_dir = data_dir
        else:
            self.app_dir = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "WordSigner")
            
        self.log_file = os.path.join(self.app_dir, "history.log")
        self.max_lines = 500
        
    def log_success(self, input_path: str, output_path: str, zone_count: int):
        nama_input  = os.path.basename(input_path)
        nama_output = os.path.basename(output_path)
        self._log(
            status="✓ BERHASIL",
            detail=(
                f"Dokumen  : {nama_input}\n"
                f"{'':>20}Output   : {nama_output}\n"
                f"{'':>20}TTD      : {zone_count} zona ditandatangani"
            )
        )

    def log_error(self, input_path: str, error: str):
        nama_input = os.path.basename(input_path) if input_path else "(tidak diketahui)"
        pesan = self._simplify_error(error)
        self._log(
            status="✗ GAGAL",
            detail=(
                f"Dokumen  : {nama_input}\n"
                f"{'':>20}Penyebab : {pesan}"
            )
        )

    def log_info(self, message: str):
        self._log(status="ℹ INFO", detail=message)

    def _log(self, status: str, detail: str):
        os.makedirs(self.app_dir, exist_ok=True)
        self._rotate_if_needed()

        ts   = datetime.now().strftime("%d %b %Y, %H:%M")
        line = f"[{ts}]  {status}\n{'':>20}{detail}\n"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _simplify_error(self, error: str) -> str:
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

        brief = str(error)
        return brief[:100] + ("..." if len(brief) > 100 else "")

    def _rotate_if_needed(self):
        if not os.path.exists(self.log_file):
            return
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > self.max_lines:
                keep = lines[len(lines) // 2:]
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.write(f"[Log dipangkas otomatis pada {datetime.now().strftime('%d %b %Y')}]\n\n")
                    f.writelines(keep)
        except Exception:
            pass
