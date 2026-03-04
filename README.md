# Word Signer

Aplikasi desktop untuk **menyisipkan tanda tangan** ke dokumen Word (`.docx`) dan mengekspornya sebagai **PDF** secara otomatis.

---

## 🚀 Quick Start

### 1. Prasyarat
- Python 3.10+
- [LibreOffice](https://www.libreoffice.org/download/) (untuk konversi PDF) — install ke lokasi default

### 2. Buat Virtual Environment
```powershell
python -m venv venv
```

### 3. Aktifkan venv
```powershell
# Windows
venv\Scripts\activate
```

### 4. Install Dependencies
```powershell
pip install -r requirements.txt
```

> **Catatan:** `cairosvg` butuh [GTK Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) di Windows untuk support SVG. Kalau tidak pakai SVG, bisa skip.

### 5. Jalankan Aplikasi
```powershell
python main.py
# atau tanpa aktifkan venv:
venv\Scripts\python.exe 
main.py
```

---

## 📂 Struktur Proyek

```
W-P-S/
├── main.py                   # Entry point (GUI)
├── requirements.txt
├── core/
│   └── config.py             # Konfigurasi global
└── services/
    ├── detector_service.py   # Deteksi zona TTD di paragraf & tabel
    ├── injector_service.py   # Sisipkan gambar TTD ke DOCX
    ├── converter_service.py  # Konversi DOCX → PDF
    ├── preset_service.py     # Simpan/load preset & settings
    └── logger_service.py     # Log riwayat operasi
```

---

## 🖥️ Cara Pakai

1. **Pilih Dokumen Word** — bisa pilih satu atau **banyak file** sekaligus (batch)
2. **Pilih Tanda Tangan** — format PNG, JPG, JPEG, atau SVG *(disimpan otomatis sebagai preset)*
3. Klik **"Buat PDF"**
4. **Pilih zona** yang akan di-TTD dari dialog preview (bisa uncheck yang tidak perlu)
5. PDF tersimpan di folder yang sama dengan nama `namafile_signed.pdf`

---

## ✨ Fitur

| Fitur | Keterangan |
|---|---|
| 🌙 Dark Mode | Toggle kanan atas — preferensi tersimpan otomatis |
| ⚙️ Settings | Atur confidence threshold, lebar TTD, dan auto-open PDF |
| ✅ Zone Preview | Preview zona sebelum proses + pilih manual mana yang di-TTD |
| 📂 Batch Mode | Proses banyak `.docx` sekaligus dengan 1 tanda tangan |
| ★ Preset TTD | TTD terakhir otomatis terisi saat buka app kembali |
| 📋 Deteksi Tabel | Zona TTD di dalam tabel Word ikut terdeteksi |
| 🔄 Fallback PDF | Jika LibreOffice gagal, otomatis coba `docx2pdf` |
| 🗒️ History Log | Riwayat tersimpan di `%APPDATA%\WordSigner\history.log` |

---

## ⚙️ Konfigurasi Default

Edit `core/config.py` atau gunakan panel Settings di aplikasi:

| Setting | Default |
|---|---|
| Confidence Threshold | `0.4` |
| Lebar TTD | `1.5` inci |
| Auto-buka PDF | `True` |

Data settings disimpan di `%APPDATA%\WordSigner\settings.json`.

---

## 📦 Dependencies

| Package | Fungsi |
|---|---|
| `python-docx` | Baca & edit file DOCX |
| `Pillow` | Konversi gambar JPG → PNG |
| `cairosvg` | Konversi SVG → PNG |
| `pymupdf` | Utility PDF |
| `docx2pdf` | Fallback converter PDF |
