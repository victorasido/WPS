# 🤖 Word Signer: Telegram Bot Edition

**Word Signer** adalah Telegram Bot canggih yang dirancang untuk menyisipkan tanda tangan ke dokumen Word (`.docx`) dan mengekspornya sebagai **PDF** secara otomatis dengan presisi tinggi.

Proyek ini telah direfaktor sepenuhnya dari aplikasi desktop menjadi bot *headless* dengan arsitektur modern yang bersih (*Clean Architecture*).

---

## ✨ Fitur Utama

- **Smart PDF Placement**: Algoritma cerdas yang memahami tata letak PDF (tabel, kolom, garis) untuk menempatkan TTD tanpa menabrak teks.
- **Auto-Crop TTD**: Secara otomatis menghapus latar belakang putih dan memotong spasi kosong pada gambar tanda tangan untuk hasil yang rapi.
- **Semantic Validation**: Menghindari kesalahan deteksi pada label formal (seperti "Dibuat oleh:") menggunakan validasi semantik.
- **Dual Injection Mode**: 
    - *Template Mode*: Mengganti placeholder gambar langsung di DOCX.
    - *Geometry Mode*: Penempatan spasial langsung di PDF (fallback cerdas).
- **History Audit**: Pencatatan riwayat transaksi melalui repositori log yang terisolasi.

---

## 🚀 Persiapan & Instalasi

### 1. Prasyarat
- **Python 3.10+**
- **LibreOffice**: Diperlukan untuk konversi Word ke PDF yang akurat. Pastikan `soffice` ada di PATH atau lokasi default.

### 2. Instalasi
```powershell
# Clone repositori dan masuk ke folder
cd W-P-S

# Buat dan aktifkan virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependensi
pip install -r requirements.txt
```

### 3. Konfigurasi Bot
Buat file bernama `.env` di root direktori dan masukkan Token Bot Telegram Anda:
```env
BOT_TOKEN=your_telegram_bot_token_here
```

---

## 🛠️ Cara Menjalankan

Jalankan bot dengan perintah:
```powershell
python bot.py
```

**Cara Menggunakan di Telegram:**
1. Kirim file dokumen **.docx** ke Bot.
2. Kirim gambar **tanda tangan** (PNG/JPG). Nama file gambar akan digunakan sebagai keyword pencarian di dokumen (contoh: `Farino Joshua.png`).
3. Bot akan memproses dan mengirimkan kembali file **PDF** yang sudah ditandatangani.

---

## 📂 Struktur Proyek (Clean Architecture)

- `bot.py`: Entry point dan controller alur Telegram.
- `services/`: Logika bisnis utama (Deteksi, Injeksi, Konversi).
- `repositories/`: Layer infrastruktur untuk I/O (Logs, Settings).
- `utils/`: Pembantu independen (Image Processing, PDF Utils, Config).
- `services/pdf_placer/`: Modul canggih untuk analisis spasial layout PDF.

---

## ⚙️ Teknologi yang Digunakan

- [python-telegram-bot](https://python-telegram-bot.org/): Framework Bot Telegram.
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/): Manipulasi dan analisis geometri PDF.
- [python-docx](https://python-docx.readthedocs.io/): Manipulasi dokumen Word.
- [Pillow](https://python-pillow.org/): Pengolahan gambar tanda tangan.

---

## ⚖️ Lisensi
Proyek ini dikembangkan untuk kebutuhan internal dan otomatisasi alur kerja dokumen secara cerdas.
