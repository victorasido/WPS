# debug_pdf.py — jalankan sekali untuk lihat teks di PDF
# Usage: python debug_pdf.py "path/to/file.pdf"

import sys
import fitz

def debug_pdf(pdf_path: str):
    doc = fitz.open(pdf_path)
    for page_num, page in enumerate(doc):
        print(f"\n{'='*60}")
        print(f"PAGE {page_num + 1}")
        print(f"{'='*60}")
        
        blocks = page.get_text("blocks")
        for i, block in enumerate(blocks):
            x0, y0, x1, y1, text, *_ = block
            text_clean = text.strip()
            if text_clean:
                print(f"  [{i:02d}] y={y0:.0f}-{y1:.0f} x={x0:.0f}-{x1:.0f} | {repr(text_clean[:80])}")

    doc.close()

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip('"')
    debug_pdf(path)