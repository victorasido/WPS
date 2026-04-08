import fitz

def rect_overlaps_text(page, rect: fitz.Rect) -> bool:
    """
    Check whether a given rect overlaps with any non-empty text span on the page.
    Returns True if overlap detected, False otherwise.
    """
    try:
        data = page.get_text("dict")
    except Exception:
        return False

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                span_rect = fitz.Rect(bbox)
                if rect.intersects(span_rect):
                    return True
    return False
