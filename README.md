# Word Signer: Headless Telegram Bot

**Word Signer Bot** adalah sistem otomatisasi penanda tanganan dokumen (Word & PDF) berbasis Telegram. Dirancang dengan **Clean Architecture**, bot ini mampu menyisipkan tanda tangan visual ke dalam dokumen dengan presisi geometris tinggi, tanpa merusak tata letak asli.

> [!IMPORTANT]
> Proyek ini telah berevolusi dari aplikasi desktop menjadi sistem _headless_ berperforma tinggi dengan fitur **Smart Layout Intelligence** yang mampu meniru penilaian estetika manusia dalam penempatan tanda tangan.

---

## 🚀 Fitur Unggulan

### 1. Smart Layout Intelligence (New!)
Bot tidak lagi sekadar menempelkan gambar di atas teks, melainkan melakukan analisis spasial mendalam:
- **Zone-Aware Adaptive Scale**: Otomatis mengecilkan TTD di formulir sempit (absen) dan membesarkannya di dokumen lebar (Memo/SK) agar proporsional.
- **Horizontal Raycasting**: Bot "menembak radar" ke kiri dan kanan untuk mencari batas kolom kosong, memastikan TTD berada tepat di tengah ruang yang tersedia.
- **Dash Boundary Adoption**: Jika terdapat garis putus-putus (`---`), bot akan menyalin koordinatnya untuk melakukan *perfect centering* layaknya editan manual.

### 2. Hybrid Session Management
Menggunakan arsitektur penyimpanan hibrida untuk kecepatan maksimal:
- **In-Memory Metadata**: Status alur kerja dan konfigurasi zona disimpan di RAM untuk respon instan.
- **SQLite BLOB Persistence**: File dokumen dan TTD disimpan di disk hanya saat terjadi perubahan, mengeliminasi bottleneck I/O disk.

### 3. Match Cascade & Semantic Validation
Algoritma deteksi cerdas yang tidak hanya mencari teks, tapi juga memvalidasi konteks:
- **Tier 1 (Exact)**: Mencari kecocokan kata yang identik.
- **Tier 2 (Regex)**: Menangani variasi tanda hubung (`-`), garis bawah (`_`), atau spasi.
- **Tier 3 (Block-Aware)**: Menggabungkan baris jabatan yang terpisah (multi-line role) tanpa menyebabkan polusi ke zona lain.

---

## 🛠 Arsitektur & Teknologi

Sistem ini menerapkan **Clean Architecture** untuk modularitas dan kemudahan pemeliharaan.

### Layer Arsitektur
- **App Layer (`src/app`)**: Handler Telegram dan orchestrator workflow.
- **Core Layer (`src/core`)**: Domain logic (Detector, Injector, Placer, Converter).
- **Infra Layer (`src/infra`)**: Repository database, telemetry (Jaeger/OTLP), dan config.
- **Shared Layer (`src/shared`)**: Utilitas PDF, Image Processing, dan Text Utilities.

### Tech Stack
- **Python 3.10+** & **python-telegram-bot** (v21.0+)
- **PyMuPDF (fitz)**: Analisis spasial & injeksi PDF tingkat rendah.
- **LibreOffice Headless**: Konversi DOCX ke PDF yang akurat.
- **OpenTelemetry & Jaeger**: Monitoring performa dan bottleneck proses.
- **Docker & Docker Compose**: Infrastruktur _isolated_.

---

## 💻 Command Cheat Sheet

Berikut adalah kumpulan perintah penting untuk operasional dan pengembangan:

### ⚙️ Manajemen Container
| Perintah | Deskripsi |
| :--- | :--- |
| `docker-compose up -d --build bot` | **Update & Rebuild**: Jalankan setelah edit kode. |
| `docker-compose stop bot` | Menghentikan bot tanpa menghapus container. |
| `docker-compose restart bot` | Restart bot dengan cepat. |
| `docker-compose down` | Mematikan seluruh layanan (Bot & Jaeger). |

### 📝 Monitoring & Debugging
| Perintah | Deskripsi |
| :--- | :--- |
| `docker-compose logs -f bot` | **Live Logs**: Pantau aktivitas bot secara real-time. |
| `docker-compose logs --tail=50 bot` | Lihat 50 baris log terakhir. |
| `docker-compose ps` | Cek status kesehatan container. |

### 🔍 Observability (Jaeger)
Setelah menjalankan sistem, buka browser dan akses:
- **Jaeger UI**: `http://localhost:16686`
- Manfaat: Lihat grafik durasi setiap tahap (Scan, Convert, Inject) untuk mencari bottleneck.

---

## 🔄 Program Flow Pipeline

| Tahap | Komponen | Deskripsi |
| :--- | :--- | :--- |
| **Ingest** | `DocumentWorkflow` | User upload file & TTD. Metadata masuk ke _MetaCache_. |
| **Scan** | `DetectorEngine` | Pencarian zona via _Block-Aware Anchor+Expand_. |
| **Inject** | `PdfPlacer` | Penentuan koordinat dengan _Raycasting_ & _Dash Bounds_. |
| **Render** | `Renderer` | Injeksi fisik dengan _Adaptive Scaling_ & _Overlap Guard_. |
| **Deliver** | `Bot` | Pengiriman dokumen final ke user. |

---

## 📂 Struktur Folder
```text
.
├── bot.py                  # Entry Point (Orchestrator)
├── src/
│   ├── app/                # Application Layer (Handlers, Workflow)
│   ├── core/               # Domain Layer (Detector, Injector, Converter)
│   ├── infra/              # Infrastructure Layer (Database, Telemetry)
│   └── shared/             # Shared Utils (PDF, Image, Text)
├── tests/                  # Automated Test Suite
└── data/                   # Persistence (SQLite, Logs, Temp Files)
```

---

## 🛠 Pengembangan & Kontribusi
1. Pastikan docker terinstal.
2. Edit file di direktori `src/`.
3. Selalu jalankan `docker-compose up -d --build bot` setelah perubahan kode core agar perubahan terefleksi di container.
