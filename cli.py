#!/usr/bin/env python3
# cli.py — Word Signer CLI
# Usage:
#   python cli.py doc.docx sign.png
#   python cli.py doc.docx sign.png --output result.pdf
#   python cli.py doc.docx sign.png --all-zones
#   python cli.py doc1.docx doc2.docx --sign sign.png

import argparse
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        prog="wordsigner",
        description="Tanda tangani dokumen Word dan ekspor ke PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python cli.py dokumen.docx ttd.png
  python cli.py dokumen.docx ttd.png --output hasil.pdf
  python cli.py dokumen.docx ttd.png --all-zones
  python cli.py doc1.docx doc2.docx --sign ttd.png
  python cli.py *.docx --sign ttd.png --all-zones
        """,
    )

    parser.add_argument(
        "docs",
        nargs="+",
        metavar="DOCX",
        help="File Word (.docx) yang akan ditandatangani. Bisa lebih dari satu.",
    )
    parser.add_argument(
        "sign",
        nargs="?",
        metavar="SIGN",
        help="File tanda tangan (png/jpg/svg). "
             "Bisa posisi argumen ke-2, atau pakai --sign.",
    )
    parser.add_argument(
        "--sign", "-s",
        dest="sign_flag",
        metavar="FILE",
        help="File tanda tangan (alternatif flag eksplisit).",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Nama output PDF. Hanya berlaku jika input satu file.",
    )
    parser.add_argument(
        "--all-zones", "-a",
        action="store_true",
        help="Pakai semua zona yang ditemukan tanpa konfirmasi interaktif.",
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Threshold confidence deteksi zona (default: 0.4).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Tampilkan log detail.",
    )

    args = parser.parse_args()

    # Resolve signature: posisi argumen atau --sign flag
    sig = args.sign_flag or args.sign

    # Heuristik: jika argumen terakhir di docs adalah file gambar,
    # anggap itu signature (backward compat dengan usage: cli.py doc.docx sign.png)
    if not sig and len(args.docs) >= 2:
        last = args.docs[-1]
        if last.lower().endswith((".png", ".jpg", ".jpeg", ".svg")):
            sig = last
            args.docs = args.docs[:-1]

    if not sig:
        parser.error(
            "File tanda tangan wajib diisi.\n"
            "  Contoh: python cli.py dokumen.docx ttd.png\n"
            "       atau: python cli.py dokumen.docx --sign ttd.png"
        )

    args.signature = sig
    return args


def resolve_docs(docs: list) -> list:
    """Expand glob pattern dan validasi file."""
    import glob
    resolved = []
    for pattern in docs:
        matches = glob.glob(pattern)
        if matches:
            resolved.extend(matches)
        else:
            resolved.append(pattern)  # biarkan error handling downstream

    valid = []
    for path in resolved:
        if not os.path.exists(path):
            print(f"  ✗ File tidak ditemukan: {path}", file=sys.stderr)
        elif not path.lower().endswith(".docx"):
            print(f"  ✗ Bukan file .docx: {path}", file=sys.stderr)
        else:
            valid.append(path)
    return valid


def pick_zones_interactive(zones: list, docx_name: str) -> list:
    """Tampilkan zona yang ditemukan dan minta user memilih."""
    print(f"\n  Ditemukan {len(zones)} zona tanda tangan di {docx_name}:")
    for i, z in enumerate(zones):
        conf  = z.get("confidence", 0)
        name  = z.get("matched_name", "-")
        badge = "✓" if conf >= 0.7 else "~"
        print(f"    [{i+1}] {badge} {name}  ({conf:.0%})")

    print()
    print("  Ketik nomor zona yang ingin ditandatangani, pisahkan koma.")
    print("  Contoh: 1,2,3   atau tekan Enter untuk semua")

    while True:
        try:
            raw = input("  Pilih zona > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Dibatalkan.")
            return []

        if not raw:
            return list(range(len(zones)))

        try:
            chosen = []
            for part in raw.split(","):
                n = int(part.strip())
                if 1 <= n <= len(zones):
                    chosen.append(n - 1)
                else:
                    raise ValueError(f"Angka {n} di luar range.")
            if chosen:
                return chosen
        except ValueError as e:
            print(f"  Input tidak valid: {e}. Coba lagi.")


def process_doc(docx_path: str, sig_path: str, args) -> str | None:
    """Proses satu file DOCX. Return path output atau None jika gagal."""
    from services.detector_service import detect_signature_zones
    from services.converter_service import convert_to_pdf
    from services.injector_service  import inject_signature
    from services.logger_service    import log_success, log_error

    docx_name = os.path.basename(docx_path)
    verbose   = args.verbose
    conf_thr  = args.confidence  # None → pakai default dari config

    # ── 1. Detect zones ──────────────────────────────────────
    print(f"  → Mendeteksi zona tanda tangan...", end=" ", flush=True)
    try:
        kwargs = {}
        if conf_thr is not None:
            kwargs["confidence_threshold"] = conf_thr
        zones = detect_signature_zones(docx_path, sig_path, **kwargs)
    except Exception as e:
        print(f"GAGAL\n  ✗ {e}")
        log_error(docx_path, str(e))
        return None

    if not zones:
        print("GAGAL")
        print(f"  ✗ Zona TTD tidak ditemukan di {docx_name}")
        log_error(docx_path, "Zona TTD tidak ditemukan.")
        return None

    print(f"{len(zones)} zona ditemukan")

    # ── 2. Pilih zona ────────────────────────────────────────
    if args.all_zones:
        selected_idx = list(range(len(zones)))
        if verbose:
            for z in zones:
                print(f"     • {z.get('matched_name', '-')}")
    else:
        selected_idx = pick_zones_interactive(zones, docx_name)
        if not selected_idx:
            return None

    selected_zones = [zones[i] for i in selected_idx]

    # ── 3. Convert DOCX → PDF ────────────────────────────────
    print(f"  → Mengkonversi ke PDF...", end=" ", flush=True)
    try:
        with open(docx_path, "rb") as f:
            docx_bytes = f.read()
        pdf_bytes = convert_to_pdf(docx_bytes)
        if verbose:
            print(f"{len(pdf_bytes):,} bytes", end=" ")
        print("OK")
    except Exception as e:
        print(f"GAGAL\n  ✗ {e}")
        log_error(docx_path, str(e))
        return None

    # ── 4. Inject signature ──────────────────────────────────
    print(f"  → Menyisipkan TTD di {len(selected_zones)} zona...", end=" ", flush=True)
    try:
        signed_pdf = inject_signature(pdf_bytes, sig_path, selected_zones)
        if verbose:
            print(f"{len(signed_pdf):,} bytes", end=" ")
        print("OK")
    except Exception as e:
        print(f"GAGAL\n  ✗ {e}")
        log_error(docx_path, str(e))
        return None

    # ── 5. Simpan output ─────────────────────────────────────
    if args.output and len(args.docs) == 1:
        output_path = args.output
    else:
        output_path = docx_path.replace(".docx", "_signed.pdf")

    try:
        with open(output_path, "wb") as f:
            f.write(signed_pdf)
    except Exception as e:
        print(f"  ✗ Gagal menyimpan: {e}")
        log_error(docx_path, str(e))
        return None

    log_success(docx_path, output_path, len(selected_zones))
    return output_path


def main():
    args = parse_args()

    # Validasi signature
    if not os.path.exists(args.signature):
        print(f"✗ File tanda tangan tidak ditemukan: {args.signature}", file=sys.stderr)
        sys.exit(1)

    # Resolve & validasi docs
    docs = resolve_docs(args.docs)
    if not docs:
        print("✗ Tidak ada file .docx valid yang ditemukan.", file=sys.stderr)
        sys.exit(1)

    # Header
    print()
    print("Word Signer CLI")
    print("─" * 40)
    print(f"  Tanda tangan : {os.path.basename(args.signature)}")
    print(f"  Dokumen      : {len(docs)} file")
    if args.all_zones:
        print(f"  Mode         : semua zona (non-interaktif)")
    print()

    # Proses semua dokumen
    success, failed = [], []

    for i, docx in enumerate(docs, 1):
        prefix = f"[{i}/{len(docs)}] " if len(docs) > 1 else ""
        print(f"{prefix}{os.path.basename(docx)}")

        output = process_doc(docx, args.signature, args)

        if output:
            size_kb = os.path.getsize(output) / 1024
            print(f"  ✓ Tersimpan: {output}  ({size_kb:.0f} KB)")
            success.append(output)
        else:
            failed.append(docx)

        if i < len(docs):
            print()

    # Summary
    print()
    print("─" * 40)
    if failed:
        print(f"  Berhasil : {len(success)} file")
        print(f"  Gagal    : {len(failed)} file")
        for f in failed:
            print(f"    ✗ {os.path.basename(f)}")
        sys.exit(1)
    else:
        if len(success) == 1:
            print(f"  ✓ Selesai — {os.path.basename(success[0])}")
        else:
            print(f"  ✓ Selesai — {len(success)} file berhasil ditandatangani")
    print()


if __name__ == "__main__":
    main()