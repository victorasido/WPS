# 🤖 Word Signer: Headless Telegram Bot

**Word Signer Bot** adalah sistem otomatisasi penanda tanganan dokumen (Word & PDF) berbasis Telegram. Dirancang dengan **Clean Architecture**, bot ini mampu menyisipkan tanda tangan visual ke dalam dokumen dengan presisi geometris tinggi, tanpa merusak tata letak asli.

> [!NOTE]
> Proyek ini telah direfaktor sepenuhnya dari aplikasi desktop menjadi layanan *containerized* yang berjalan secara *headless* di server/Docker dengan arsitektur yang modular.

---

## 🏗️ Arsitektur & Teknologi

Sistem ini menerapkan **Clean Architecture** untuk memastikan kode mudah diuji, dipelihara, dan independen terhadap framework luar.

### Layer Arsitektur
- **App Layer (`src/app`)**: Berisi handler Telegram dan workflow orkestrasi dokumen.
- **Core Layer (`src/core`)**: Logika bisnis utama (Detection, Injection, PDF Placement, Validation).
- **Infra Layer (`src/infra`)**: Implementasi detail teknis seperti Database (Repositories), Telemetri, dan Konfigurasi.
- **Shared Layer (`src/shared`)**: Utilitas umum yang digunakan di lintas layer.

### Tech Stack
- **Core**: Python 3.10+
- **Telegram Framework**: [python-telegram-bot](https://python-telegram-bot.org/) (v21.0+)
- **PDF Engine**: [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) — Digunakan untuk analisis tata letak spasial dan injeksi gambar.
- **Office Engine**: [LibreOffice Headless](https://www.libreoffice.org/) — Menjamin konversi DOCX ke PDF yang akurat.
- **Observability**: [OpenTelemetry](https://opentelemetry.io/) — Tracing untuk memantau bottleneck pemrosesan.
- **Infrastruktur**: Docker & Docker Compose.

---

## 🔄 Program Flow

Proses penanda tanganan mengikuti *pipeline* yang ketat:

| Tahap | Komponen | Deskripsi | Hasil |
|:--- |:--- |:--- |:--- |
| **1. Ingest** | `DocumentWorkflow` | User upload Dokumen (.docx/.pdf) & TTD (.png/.jpg) | Session Created |
| **2. Scan** | `DetectorEngine` | Mencari area tanda tangan menggunakan *Match Cascade* & Regex | List Target Zones |
| **3. Convert** | `ConverterService` | Konversi DOCX ke PDF via LibreOffice (Skip jika input PDF) | PDF Bytes |
| **4. Inject** | `PdfPlacer` | Menyisipkan TTD dengan *Geometric & Layout-Aware Constraints* | Signed PDF |
| **5. Deliver** | `Bot -> User` | Mengirimkan dokumen final ke chat Telegram | Dokumen Selesai ✅ |

---

## ✨ Fitur Unggulan

### 1. Match Cascade & Semantic Validation
Algoritma deteksi cerdas yang tidak hanya mencari teks, tapi juga memvalidasi konteks:
- **Tier 1 (Exact)**: Mencari kecocokan kata yang identik.
- **Tier 2 (Regex)**: Menangani variasi tanda hubung (`-`), garis bawah (`_`), atau spasi.
- **Tier 3 (Semantic)**: Memastikan area yang ditemukan adalah area tanda tangan (misal: ada garis penutup).

### 2. Layout-Aware Geometry
Penyisipan tanda tangan menggunakan perhitungan spasial tingkat lanjut:
- **Empty Slot Detection**: Menghitung area putih di sekitar keyword untuk menentukan tinggi ideal TTD.
- **Scaling Constraints**: TTD secara otomatis di-*resize* agar tetap proporsional (maks 160x80pt).
- **Table Support**: Mampu mendeteksi dan menyisipkan TTD di dalam sel tabel tanpa merusak garis tabel.

### 3. Transparent PDF Processing
Sistem mendukung penuh file PDF asli. Jika dokumen input adalah PDF, bot akan langsung melakukan scanning tanpa melalui tahap konversi Office, menjaga integritas file asli.

---

## 🚀 Deployment (Docker Compose)

### 1. Konfigurasi
Buat file `.env` di root direktori:
```env
BOT_TOKEN=your_telegram_bot_token_here
DATA_DIR=/app/data
APP_ENV=production
```

### 2. Jalankan Service
```bash
docker-compose up -d --build
```

---

## 📂 Struktur Folder
```text
.
├── bot.py                  # Entry Point (Orchestrator)
├── src/
│   ├── app/                # Application Layer
│   │   └── handlers/       # Telegram Command & Workflow Handlers
│   ├── core/               # Domain/Business Logic
│   │   ├── detector/       # Keyword & Zone Detection
│   │   ├── injector/       # Core Injection Logic
│   │   ├── pdf_placer/     # Spatial Layout Analysis
│   │   └── converter/      # Office to PDF Conversion
│   ├── infra/              # Infrastructure Layer
│   │   ├── database/       # File & Session Repositories
│   │   └── telemetry/      # OpenTelemetry Setup
│   └── shared/             # Shared Utilities (PDF, Image, Text)
├── tests/                  # Automated Test Suite
└── data/                   # Persistence Volume (Logs, Docs, Temps)
```

---

## ⚖️ Lisensi
Dikembangkan untuk internal BNI (Bank Negara Indonesia) guna mempercepat alur kerja dokumen digital secara cerdas dan otomatis.
