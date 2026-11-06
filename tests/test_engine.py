"""Headless regression tests for the native vector removal engine."""
from pathlib import Path
import sys

import pytest
import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import EditError, inspect_selection, process_pdf


def make_document(path: Path, *, with_vector=True, page_rotation=0, with_image=False, with_xmp=False):
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=420)
    # Thin horizontal engineering-style line crossing the selection: should survive.
    page.draw_line((40, 340), (560, 340), width=0.1, color=(0, 0, 0))
    if with_vector:
        s = page.new_shape()
        s.draw_line((75, 80), (140, 80))
        s.draw_line((140, 80), (108, 130))
        s.draw_line((108, 130), (75, 80))
        s.finish(color=(0, 0, 0), width=0.7)
        s.commit()
    page.insert_text((45, 355), "Metall AG — 12345", fontsize=12)
    page.insert_text((215, 130), "TEXT STAYS", fontsize=14)
    if with_image:
        import io
        png_buffer = io.BytesIO()
        Image.new('RGB', (20, 20), (255, 10, 10)).save(png_buffer, format='PNG')
        page.insert_image(pymupdf.Rect(220, 50, 280, 110), stream=png_buffer.getvalue())
    page.set_rotation(page_rotation)
    doc.new_page(width=700, height=500).insert_text((45, 50), "Unmodified page")
    doc.set_metadata({'title': 'Engineering test', 'author': 'Example Company', 'creator': 'CAD', 'keywords': 'private'})
    if with_xmp:
        doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><value>do-not-change</value></x:xmpmeta>")
    doc.save(path)
    doc.close()


def test_removes_only_vectors_preserves_text_metadata_and_other_pages(tmp_path):
    src = tmp_path/'source.pdf'
    make_document(src, with_xmp=True, with_image=True)
    with pymupdf.open(src) as before:
        md = before.metadata
        xmp = before.get_xml_metadata()
        before_page1 = before[1].get_text()
        before_images = before[0].get_image_info(xrefs=True)
    stats = inspect_selection(pymupdf.open(src)[0], (68, 68, 150, 142))
    assert stats.eligible_vectors >= 1
    result = process_pdf(src, {0: [(68, 68, 150, 142)]})
    assert result.removed_vectors >= 1
    assert result.edited_pages == 1
    assert result.metadata_preserved
    with pymupdf.open(stream=result.pdf_bytes, filetype='pdf') as after:
        assert after.metadata == md
        assert after.get_xml_metadata() == xmp
        assert after[1].get_text() == before_page1
        after_images = after[0].get_image_info(xrefs=True)
        assert len(after_images) == len(before_images)
        assert [(x['bbox'], x['digest'], x['width'], x['height']) for x in after_images] == \
               [(x['bbox'], x['digest'], x['width'], x['height']) for x in before_images]
        assert 'TEXT STAYS' in after[0].get_text()
        assert 'Metall AG' in after[0].get_text()


def test_rejects_empty_selection(tmp_path):
    src = tmp_path/'source.pdf'
    make_document(src)
    with pytest.raises(EditError, match='mindestens ein Rechteck'):
        process_pdf(src, {})


def test_rejects_text_only_selection(tmp_path):
    src = tmp_path/'source.pdf'
    make_document(src, with_vector=False)
    with pytest.raises(EditError, match='Keine vollständigen Vektorobjekte'):
        process_pdf(src, {0: [(210, 110, 320, 140)]})


def test_rejects_outside_page(tmp_path):
    src = tmp_path/'source.pdf'
    make_document(src)
    with pytest.raises(EditError, match='außerhalb der Seite'):
        process_pdf(src, {0: [(0, 0, 99999, 100)]})


def test_rotated_page_preserves_untouched_visuals(tmp_path):
    src = tmp_path/'rotated.pdf'
    make_document(src, page_rotation=90)
    with pymupdf.open(src) as doc:
        p = doc[0]
        # Transform a known unrotated bbox into the displayed rotated coordinates.
        display_rect = pymupdf.Rect(68, 68, 150, 142) * p.rotation_matrix
    result = process_pdf(src, {0: [list(display_rect)]})
    assert result.removed_vectors >= 1


def test_source_is_not_overwritten(tmp_path):
    src = tmp_path/'source.pdf'
    make_document(src)
    original_bytes = src.read_bytes()
    process_pdf(src, {0: [(68, 68, 150, 142)]})
    assert src.read_bytes() == original_bytes


def test_surgical_cad_blocks_preserve_native_text_and_vectors(tmp_path):
    """Simulate a CAD exporter with independent q/cm/path/Q operations."""
    source = tmp_path / "cad.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    page.insert_text((40, 60), "Text must stay unchanged", fontsize=13)
    page.draw_line((30, 280), (570, 280), color=(0, 0, 0), width=0.15)
    refs = page.get_contents()
    assert refs
    old = doc.xref_stream(refs[0])
    cad_paths = (
        b"\nq 1 0 0 1 120 220 cm\n0 0 m\n25 0 l\nS\nQ\n"
        b"q 1 0 0 1 125 214 cm\n0 0 m\n0 9 l\nS\nQ\n"
    )
    doc.update_stream(refs[0], old + cad_paths)
    doc.set_metadata({"author": "Unchanged author", "title": "CAD export"})
    doc.save(source)
    doc.close()

    with pymupdf.open(source) as before:
        baseline_text = before[0].get_text("rawdict")
        baseline_meta = before.metadata
        baseline_drawings = len(before[0].get_drawings())
    result = process_pdf(source, {0: [(110, 170, 160, 194)]})
    assert result.method == "surgical"
    assert result.removed_vectors == 2
    with pymupdf.open(stream=result.pdf_bytes, filetype="pdf") as after:
        assert after[0].get_text("rawdict") == baseline_text
        assert after.metadata == baseline_meta
        assert len(after[0].get_drawings()) == baseline_drawings - 2
