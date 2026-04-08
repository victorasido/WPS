import pytest
import fitz
from src.core.injector.renderer import insert_image as _insert_image
from src.core.injector.scanners import SIGNATURE_PADDING
import src.core.injector.renderer as renderer_module


class MockPage:
    def __init__(self, width=600, height=800):
        self.width = width
        self.height = height
        self.injected_images = []

    def insert_image(self, rect, stream=None):
        self.injected_images.append(rect)


def test_insert_image_scaling():
    """Test image insertion with scaling constraints."""
    from unittest.mock import MagicMock

    page      = MockPage()
    rect      = fitz.Rect(100, 100, 700, 500)  # Large zone 600×400
    sig_bytes = b"fake_png"

    # Mock SignatureImageProcessor and rect_overlaps_text at their real location
    original_processor = renderer_module.SignatureImageProcessor
    original_overlaps  = renderer_module.rect_overlaps_text

    mock_inst = MagicMock()
    mock_inst.process.return_value = (sig_bytes, 100, 100)
    renderer_module.SignatureImageProcessor = MagicMock(return_value=mock_inst)
    renderer_module.rect_overlaps_text = MagicMock(return_value=False)

    try:
        _insert_image(page, rect, sig_bytes)

        assert len(page.injected_images) == 1
        img_rect = page.injected_images[0]

        # Max scale=2.0 but absolute cap: 160×80pt.
        # 100×100 * 2.0 = 200×200 → violates 80pt height cap.
        # target_w = min(600*0.85, 160) = 160
        # target_h = min(400*0.85, 80)  = 80
        # max_scale = min(160/100, 80/100, 2.0) = 0.8
        # So 100×100 * 0.8 = 80×80
        assert img_rect.width  == 80.0
        assert img_rect.height == 80.0

        # rect width=600. cx = 100 + (600 - 80)/2 = 100 + 260 = 360
        assert img_rect.x0 == 360.0
        # Bottom-aligned: y1=500. cy = max(100, 500-80) = 420
        assert img_rect.y0 == 420.0

    finally:
        renderer_module.SignatureImageProcessor = original_processor
        renderer_module.rect_overlaps_text      = original_overlaps


def test_insert_image_shrink_to_fit():
    """Test image fallback to min_scale when zone is too small."""
    from unittest.mock import MagicMock

    page      = MockPage()
    rect      = fitz.Rect(100, 100, 140, 120)  # Tiny zone 40×20
    sig_bytes = b"fake_png"

    original_processor = renderer_module.SignatureImageProcessor
    original_overlaps  = renderer_module.rect_overlaps_text

    mock_inst = MagicMock()
    mock_inst.process.return_value = (sig_bytes, 100, 100)
    renderer_module.SignatureImageProcessor = MagicMock(return_value=mock_inst)
    renderer_module.rect_overlaps_text = MagicMock(return_value=False)

    try:
        _insert_image(page, rect, sig_bytes)
        img_rect = page.injected_images[0]

        # target_w = min(40*0.85, 160) = 34
        # target_h = min(20*0.85, 80)  = 17
        # max_scale = min(34/100, 17/100, 2.0) = 0.17
        # max_scale < min_scale (0.4) → clipped to min_scale = 0.4
        # → 100×100 * 0.4 = 40×40
        assert img_rect.width  == 40.0
        assert img_rect.height == 40.0

    finally:
        renderer_module.SignatureImageProcessor = original_processor
        renderer_module.rect_overlaps_text      = original_overlaps
