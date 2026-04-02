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
