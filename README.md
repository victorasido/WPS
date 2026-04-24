# Word Signer: Headless Telegram Bot

**Word Signer Bot** adalah sistem otomatisasi penanda tanganan dokumen (Word & PDF) berbasis Telegram. Dirancang dengan **Clean Architecture**, bot ini mampu menyisipkan tanda tangan visual ke dalam dokumen dengan presisi geometris tinggi, tanpa merusak tata letak asli.

> [!IMPORTANT]
> Proyek ini telah berevolusi dari aplikasi desktop menjadi sistem _headless_ berperforma tinggi dengan fitur **Smart Layout Intelligence** yang mampu meniru penilaian estetika manusia dalam penempatan tanda tangan, dan kini dilengkapi dengan **Stabilitas Infrastruktur Tingkat Produksi**.

---

## 🚀 Fitur Unggulan

### 1. Smart Layout Intelligence
Bot tidak lagi sekadar menempelkan gambar di atas teks, melainkan melakukan analisis spasial mendalam:
- **Zone-Aware Adaptive Scale**: Otomatis mengecilkan TTD di formulir sempit (absen) dan membesarkannya di dokumen lebar (Memo/SK) agar proporsional.
- **Horizontal Raycasting**: Bot "menembak radar" ke kiri dan kanan untuk mencari batas kolom kosong, memastikan TTD berada tepat di tengah ruang yang tersedia.
- **Dash Boundary Adoption**: Jika terdapat garis putus-putus (`---`), bot akan menyalin koordinatnya untuk melakukan *perfect centering* layaknya editan manual.

### 2. Hybrid Session Management
Menggunakan arsitektur penyimpanan hibrida untuk kecepatan maksimal dan efisiensi memori (mencegah *Memory Leak*):
- **In-Memory Metadata**: Status alur kerja dan konfigurasi zona disimpan di RAM untuk respon instan.
- **SQLite BLOB Persistence**: File dokumen dan TTD disimpan di disk SQLite hanya saat terjadi perubahan, mengeliminasi bottleneck I/O disk dan menjaga kestabilan RAM server.

### 3. Production-Ready Infrastructure (Lean & Stable)
Sistem dilengkapi pengaman untuk mencegah beban berlebih (Overload) dengan struktur yang sangat ramping:
- **Concurrency Control**: Dilengkapi *LibreOffice Conversion Queue* berbasis `asyncio.Semaphore`. Mencegah server *crash* akibat OOM (Out of Memory) jika banyak pengguna memproses dokumen serentak dengan antrean otomatis.
- **Docker Resource Limits**: Container bot dibatasi secara *hard-limit* (RAM dan CPU) untuk perlindungan OS tingkat lanjut.
- **Polling & Webhook**: Mendukung mode polling untuk *development* dan **Webhook Mode** untuk *production* guna menghemat penggunaan CPU.

### 4. Match Cascade & Semantic Validation
Algoritma deteksi cerdas yang tidak hanya mencari teks, tapi juga memvalidasi konteks:
- **Tier 1 (Exact)**: Mencari kecocokan kata yang identik.
- **Tier 2 (Regex)**: Menangani variasi tanda hubung (`-`), garis bawah (`_`), atau spasi.
- **Tier 3 (Block-Aware)**: Menggabungkan baris jabatan yang terpisah (multi-line role) tanpa menyebabkan polusi ke zona lain.

---

## 💬 Alur Interaksi Bot

Sistem menggunakan *Conversational State Machine* untuk memastikan alur kerja yang intuitif bagi pengguna:

1.  **Inisiasi**: Kirim perintah `/sign` atau gunakan perintah `/start` untuk melihat menu utama.
2.  **Kirim Dokumen**: Bot meminta file `.docx` atau `.pdf`. Sistem akan langsung melakukan validasi format.
3.  **Kirim Tanda Tangan**: Kirim gambar TTD (disarankan sebagai file agar HD). Bot **otomatis mengambil keyword** dari nama file TTD (contoh: `Direktur Utama.png` -> mencari teks "Direktur Utama").
4.  **Konfirmasi Zona**:
    - **Mode DOCX**: Bot menampilkan daftar koordinat teks yang ditemukan. Anda bisa memilih satu atau banyak zona. Jika server sedang memproses dokumen lain, Anda akan dimasukkan ke dalam **sistem antrean** *(Queue)* secara otomatis.
    - **Mode PDF**: Bot melakukan *fast-scan* dan injeksi langsung menggunakan algoritma raycasting.
5.  **Pengiriman**: Bot mengirimkan dokumen PDF final yang sudah ditandatangani.

> [!TIP]
> Anda dapat memicu pembatalan sesi kapan saja dengan perintah `/cancel` atau melihat panduan detail dengan `/help`.

---

## 🛠 Arsitektur & Teknologi

Sistem ini menerapkan **Clean Architecture** untuk modularitas dan kemudahan pemeliharaan. Kode dirancang sangat ramping tanpa *boilerplate* yang tidak perlu.

### Layer Arsitektur
- **App Layer (`src/app`)**: Handler Telegram, manajemen status pengguna, dan UI Messages.
- **Core Layer (`src/core`)**: Domain logic murni (Detector, Injector, Placer, Converter). Bebas dari _vendor lock-in_ Telegram.
- **Infra Layer (`src/infra`)**: Repository database (SQLite), antrean konverter, dan config.
- **Shared Layer (`src/shared`)**: Utilitas PDF, Image Processing, dan Text Utilities.

### Tech Stack
- **Python 3.10+** & **python-telegram-bot** (v21.0+)
- **PyMuPDF (fitz)**: Analisis spasial & injeksi PDF tingkat rendah.
- **LibreOffice Headless**: Konversi DOCX ke PDF yang akurat.
- **Docker & Docker Compose**: Infrastruktur _isolated_ dengan manajemen sumber daya (Resource Limit).

---

## ⚡ Persiapan Cepat (Quick Start)

1. **Clone Repositori**:
   ```bash
   git clone <repository-url>
   cd W-P-S
   ```

2. **Setup Environment**:
   Salin file contoh konfigurasi dan isi parameter sesuai kebutuhan.
   ```bash
   cp .env.example .env
   ```

3. **Jalankan dengan Docker**:
   Pastikan Docker Desktop sudah aktif, lalu jalankan:
   ```bash
   docker-compose up -d --build
   ```

---

## 🔧 Konfigurasi (.env)

Berikut adalah variabel-variabel kunci di `.env`:

| Variabel | Deskripsi | Default |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Token API Bot Telegram bawaan dari [@BotFather](https://t.me/BotFather). | - (Wajib) |
| `APP_ENV` | Mode lingkungan (`development` atau `production`). | `development` |
| `DATA_DIR` | Direktori lokal (*bind-mounted*) untuk SQLite & File Logs. | `./data` |
| `MAX_CONVERSIONS` | Batas keamanan maksimum pemrosesan paralel LibreOffice. Jika tidak di-set, runtime memakai default `1` di `production` dan `3` di `development`. | `auto` |
| `LIBREOFFICE_TIMEOUT` | Timeout subprocess LibreOffice dalam detik agar konversi tidak menggantung tanpa batas. | `180` / `300` |
| `TELEGRAM_CONNECT_TIMEOUT` | Timeout koneksi ke Telegram API. | `30` |
| `TELEGRAM_READ_TIMEOUT` | Timeout baca response Telegram API, terutama saat download/upload file besar. | `180` |
| `TELEGRAM_WRITE_TIMEOUT` | Timeout kirim body request Telegram API. | `180` |
| `TELEGRAM_POOL_TIMEOUT` | Timeout antrean koneksi HTTP Telegram API. | `30` |
| `USE_WEBHOOK` | Mode hemat CPU (*Production*). Ganti ke `true` untuk aktif. Membutuhkan Domain Publik + SSL. | `false` |
| `WEBHOOK_URL` | URL Endpoint penerima *update* dari Telegram. | - |
| `WEBHOOK_PORT` | Port internal aplikasi yang mendengarkan request dari Webhook. | `8443` |

---

## 🐳 Panduan Operasional Docker (Cheat Sheet)

Mengingat arsitektur aplikasi bergantung pada lingkungan isolasi *(containerized)*, berikut adalah perintah esensial untuk memanajemen *lifecycle* pelayanan bot menggunakan terminal atau Docker Desktop.

### ⚙️ Manajemen Siklus Hidup (Lifecycle)
| Perintah | Deskripsi |
| :--- | :--- |
| `docker-compose up -d` | **Start**: Menjalankan *bot* di *background* (*detached mode*). |
| `docker-compose up -d --build` | **Rebuild**: Wajib dijalankan apabila Anda melakukan modifikasi di `src/`, mengubah file `Dockerfile`, atau me-refresh `requirements.txt`. |
| `docker-compose restart` | Memulai ulang bot (berguna jika konfigurasi `.env` baru saja dirubah). |
| `docker-compose stop` | Menghentikan bot sementara (membiarkan jaringan internal utuh). |
| `docker-compose down` | **Tear Down**: Mematikan dan membuang wadah kontainer (*destroy*) beserta jaringannya. Tidak akan menghapus basis data SQLite di folder `data/`. |

### 📝 Observasi & Telemetri Log
| Perintah | Deskripsi |
| :--- | :--- |
| `docker-compose logs -f` | **Live Logs**: Duduk dan pantau obrolan Telegram di balik layar. Sangat penting untuk melihat antrean eksekusi *Semaphore Lock*. |
| `docker-compose logs --tail=50` | Hanya mencetak 50 baris interaksi terakhir agar terminal tidak banjir log. |
| `docker stats wordsigner_bot` | **Resource Monitoring**: Melihat grafik konsumsi RAM dan CPU terkini. Sangat krusial untuk memastikan tidak memakan jatah memori melampaui setelan _Limit_ (`1GB`). |

### 🛠 Skala Produksi Ekstensif & Pemeliharaan
| Perintah | Deskripsi |
| :--- | :--- |
| `docker-compose exec bot /bin/bash` | **Masuk (SSH) ke dalam Bot**: Berguna apabila Anda mau meriset file di dalam Ubuntu Server virtual bot secara langsung. (Ketik `exit` untuk keluar). |
| `docker system prune -a --volumes` | **Hard Reset (Pembersihan Ekstrem)**: Hapus sistem *cache docker*, gambar usang, lalu _deploy_ ulang ruang memori Anda (jika memori SSD Anda penuh). |

---

## 📂 Struktur Folder
```text
.
├── bot.py                  # Entry Point (Menyediakan fitur Polling / Webhook switch)
├── src/
│   ├── app/                # Application Layer (Handlers, State Machine, UI Messages)
│   ├── core/               # Domain Layer (Detector, Injector, Converter)
│   ├── infra/              # Infrastructure Layer (Hybrid Storage, Queue Semaphore)
│   └── shared/             # Shared Layer (PDF & Image Utilities)
└── data/                   # Bind-Mount Persistence Storage
```

---

## Workflow Diagram (Ringkasan State)

| State | Kondisi User | Sistem | Rute Berikutnya |
| --- | --- | --- | --- |
| **WAIT_DOCX** | Mengutus file `.docx` / `.pdf` | Ekstrak Metadata → Simpan ke SQLite | **WAIT_SIGN** |
| **WAIT_SIGN** | Mengutus TTD Mentah | Pungut Label Ekstensi Nama | _Run Detect_ **(Jika PDF: Fast Bypass)** |
| **WAIT_ZONE_SELECT** | Mencentang Koordinat Target | Masuk *Conversion Queue* → Injeksi TTD | Kirim Berkas Akhir → Akhiri Sesi |
| **Any state** | Perintah `/cancel` | Menghapus Sesi In-Memory & Database | Akhiri Sesi |

_Catatan: Apabila sesi kadaluwarsa, jalankan instruksi `/sign` untuk me-reset ulang sistem alur kerja._
