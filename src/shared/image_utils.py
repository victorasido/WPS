import io
from PIL import Image


def remove_image_background(img: Image.Image) -> bytes:
    """
    Hapus background putih/terang dari gambar TTD.
    Pixel dengan brightness > 240 (hampir putih) → transparan.
    Hasilnya TTD terlihat bersih di atas PDF tanpa kotak putih.
    """
    img  = img.convert("RGBA")
    data = img.getdata()

    new_data = []
    for r, g, b, a in data:
        # Pixel terang (putih/near-white) → transparan
        if r > 240 and g > 240 and b > 240:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append((r, g, b, a))

    img.putdata(new_data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class SignatureImageProcessor:
    """
    SRP: Tanggung jawab tunggal memproses gambar TTD sebelum di-sisipkan ke PDF.

    Komposisi dipakai oleh injector_service._insert_image, bukan inheritance.

    Pipeline:
        1. Hapus background putih/terang (remove_image_background)
        2. Crop canvas transparan berlebih menggunakan Pillow getbbox()
           → fix: iw/ih yang dikirim ke kalkulasi skala adalah ukuran gambar
             yang sesungguhnya, bukan ukuran canvas penuh yang kosong.
    """

    def process(self, raw_bytes: bytes) -> tuple:
        """
        Terima raw image bytes (PNG/JPG/RGBA),
        return (processed_bytes: bytes, width: int, height: int).
        Width dan height adalah ukuran SETELAH crop — bukan ukuran canvas asli.
        """
        img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")

        # Step 1: Hapus background putih
        cleaned_bytes = remove_image_background(img)

        # Step 2: Re-open untuk crop transparan
        img_clean = Image.open(io.BytesIO(cleaned_bytes)).convert("RGBA")

        # Step 3: Crop canvas transparan berlebih menggunakan getbbox()
        bbox = img_clean.getbbox()
        if bbox:
            img_clean = img_clean.crop(bbox)

        # Step 4: Serialize hasil akhir
        buf = io.BytesIO()
        img_clean.save(buf, format="PNG")
        final_bytes = buf.getvalue()
        w, h = img_clean.size

        return final_bytes, w, h


def prepare_signature(path: str) -> bytes:
    """
    Muat file tanda tangan dari disk dan return sebagai PNG bytes.
    Mendukung format SVG (dikonversi via cairosvg) dan raster (PNG/JPG).
    """
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "svg":
        import cairosvg
        return cairosvg.svg2png(url=path)
    img = Image.open(path).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
