"""Universal rectangle removal: text, embedded images, scans and safety failures."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

import pytest
import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from universal import process_pdf_universal
from engine import EditError


def make_image(width=160, height=120):
    im = Image.new("RGB", (width, height), "white")
    dr = ImageDraw.Draw(im)
    dr.rectangle((20, 20, width - 20, height - 20), fill=(185, 10, 20))
    dr.text((30, 35), "LOGO", fill="white")
    data = BytesIO()
    im.save(data, "PNG")
    return data.getvalue()


def open_output(res):
    return pymupdf.open(stream=res.pdf_bytes, filetype="pdf")


def base(tmp_path, kind="text", xmp=True):
    file = tmp_path / f"{kind}.pdf"
    d = pymupdf.open()
    p = d.new_page(width=600, height=400)
    p.insert_text((55, 50), "KEEP CONTENT", fontsize=12)
    p.draw_line((30, 320), (570, 320), color=(0, 0, 0), width=0.15)
    imgdata = make_image()
    if kind == "text":
        p.insert_text((110, 115), "SECRET LOGO", fontsize=20)
    elif kind == "image":
        p.insert_image(pymupdf.Rect(300, 100, 460, 220), stream=imgdata)
    elif kind == "scan":
        # A scanned page is already an image; only its pixels inside the rectangle change.
        p.insert_image(p.rect, stream=make_image(600, 400))
    elif kind == "mixed":
        p.insert_text((110, 115), "SECRET LOGO", fontsize=20)
        p.insert_image(pymupdf.Rect(300, 100, 460, 220), stream=imgdata)
        p.draw_rect(pymupdf.Rect(110, 155, 200, 190), color=(1, 0, 0), width=0.5)
    elif kind == "crossing":
        p.draw_line((200, 140), (500, 140), width=0.6)
    elif kind == "reused":
        xref = p.insert_image(pymupdf.Rect(300, 100, 460, 220), stream=imgdata)
        p.insert_image(pymupdf.Rect(100, 200, 260, 320), xref=xref)
    d.set_metadata({"title": "Test", "author": "Example Publisher", "keywords": "confidential"})
    if xmp:
        d.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><test>identical</test></x:xmpmeta>")
    d.save(file)
    d.close()
    return file


def test_text_deleted_native_with_other_text_metadata_preserved(tmp_path):
    src = base(tmp_path, "text")
    with pymupdf.open(src) as before:
        metadata = before.metadata
        xmp = before.get_xml_metadata()
    result = process_pdf_universal(src, {0: [(105, 88, 260, 120)]})
    assert result.method == "universal"
    assert result.removed_text_chars == len("SECRET LOGO")
    with open_output(result) as clean:
        assert "SECRET" not in clean[0].get_text()
        assert "KEEP CONTENT" in clean[0].get_text()
        assert clean.metadata == metadata
        assert clean.get_xml_metadata() == xmp


def test_full_image_object_deleted(tmp_path):
    src = base(tmp_path, "image")
    result = process_pdf_universal(src, {0: [(295, 95, 465, 225)]})
    assert result.modified_images == 1
    with open_output(result) as clean:
        assert not clean[0].get_image_info(xrefs=True)
        assert "KEEP CONTENT" in clean[0].get_text()


def test_partial_image_replaced_without_rasterizing_other_pdf_content(tmp_path):
    src = base(tmp_path, "image")
    with pymupdf.open(src) as original:
        digest = original[0].get_image_info(xrefs=True)[0]["digest"]
    result = process_pdf_universal(src, {0: [(340, 130, 420, 195)]})
    with open_output(result) as clean:
        images = clean[0].get_image_info(xrefs=True)
        assert len(images) == 1
        assert images[0]["digest"] != digest
        assert "KEEP CONTENT" in clean[0].get_text()
        assert len(clean[0].get_drawings()) == 1  # thin native PDF line


def test_scanned_page_subset_rewritten_without_flattening_page(tmp_path):
    src = base(tmp_path, "scan")
    result = process_pdf_universal(src, {0: [(100, 85, 250, 190)]})
    assert result.modified_images == 1
    with open_output(result) as clean:
        assert len(clean[0].get_image_info(xrefs=True)) == 1
        assert "KEEP CONTENT" in clean[0].get_text()
        assert len(clean[0].get_drawings()) == 1


def test_mixed_text_vector_image_in_two_rectangles(tmp_path):
    src = base(tmp_path, "mixed")
    result = process_pdf_universal(src, {0: [(105, 88, 260, 194), (295, 95, 465, 225)]})
    assert result.removed_text_chars >= 6
    assert result.modified_images == 1
    assert result.removed_vectors >= 1
    with open_output(result) as clean:
        assert "SECRET" not in clean[0].get_text()
        assert "KEEP CONTENT" in clean[0].get_text()
        assert len(clean[0].get_drawings()) == 1


def test_vector_only_uses_existing_precision_engine(tmp_path):
    src = tmp_path / "vector.pdf"
    d = pymupdf.open()
    p = d.new_page(width=400, height=300)
    p.draw_rect(pymupdf.Rect(100, 100, 160, 160), color=(0, 0, 0))
    p.insert_text((200, 70), "KEEP", fontsize=12)
    d.save(src)
    d.close()
    result = process_pdf_universal(src, {0: [(90, 90, 170, 170)]})
    assert result.removed_vectors >= 1
    assert result.method in ("surgical", "native")


def test_crossing_vector_rejected_no_output(tmp_path):
    src = base(tmp_path, "crossing")
    with pytest.raises(EditError, match="überschneiden den Rand"):
        process_pdf_universal(src, {0: [(245, 120, 360, 160)]})


def test_shared_image_rejected_for_privacy(tmp_path):
    src = base(tmp_path, "reused")
    with pytest.raises(EditError, match="mehrfach verwendet"):
        process_pdf_universal(src, {0: [(295, 95, 465, 225)]})


def test_original_is_never_overwritten(tmp_path):
    src = base(tmp_path, "image")
    raw = src.read_bytes()
    process_pdf_universal(src, {0: [(340, 130, 420, 195)]})
    assert src.read_bytes() == raw
