"""Regression tests for the intelligent and text-only modes (table-safe editing)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

import pytest
import pymupdf
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import EditError
from text_only import process_pdf_text_only, process_pdf_intelligent
from universal import process_pdf_universal


def make_table(tmp_path: Path, rotated: bool = False) -> Path:
    source = tmp_path / ('table_rotated.pdf' if rotated else 'table.pdf')
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    # Single connected vector drawing spans the selected text and neighboring cells.
    grid = page.new_shape()
    grid.draw_rect(pymupdf.Rect(50, 80, 530, 220))
    grid.draw_line((250, 80), (250, 220))
    grid.draw_line((50, 150), (530, 150))
    grid.finish(color=(0, 0, 0), width=0.4)
    grid.commit()
    page.insert_text((75, 137), 'BLEIBT', fontsize=15)
    page.insert_text((266, 137), 'VERTRAULICH', fontsize=15)
    page.insert_text((266, 196), 'UNTEN BLEIBT', fontsize=15)
    page.insert_text((60, 300), 'TECHNISCHE ZEICHNUNG', fontsize=10)
    img = Image.new('RGB', (28, 28), '#1564A7')
    b = BytesIO()
    img.save(b, 'PNG')
    page.insert_image(pymupdf.Rect(550, 35, 578, 63), stream=b.getvalue())
    if rotated:
        page.set_rotation(90)
    doc.set_metadata({'title': 'Tabelle', 'author': 'Example Publisher', 'keywords': 'metadata'})
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'><memo>Unverändert</memo></x:xmpmeta>")
    doc.save(source)
    doc.close()
    return source


TABLE_RECT = pymupdf.Rect(258, 117, 443, 168)  # intersects the middle table grid line


def verify_table_clean(result, source):
    with pymupdf.open(source) as before, pymupdf.open(stream=result.pdf_bytes, filetype='pdf') as clean:
        assert 'VERTRAULICH' not in clean[0].get_text()
        assert 'BLEIBT' in clean[0].get_text()
        assert 'UNTEN BLEIBT' in clean[0].get_text()
        assert before[0].get_drawings() == clean[0].get_drawings(), 'Every table vector must remain'
        assert [(i['digest'], i['bbox'], i['width'], i['height']) for i in before[0].get_image_info(xrefs=True)] == [(i['digest'], i['bbox'], i['width'], i['height']) for i in clean[0].get_image_info(xrefs=True)]
        assert before.metadata == clean.metadata
        assert before.get_xml_metadata() == clean.get_xml_metadata()


def test_text_only_deletes_cell_text_preserving_table_lines(tmp_path):
    src = make_table(tmp_path)
    result = process_pdf_text_only(src, {0: [TABLE_RECT]})
    assert result.method == 'text_only'
    assert result.removed_vectors == 0
    assert result.modified_images == 0
    assert result.removed_text_chars == len('VERTRAULICH')
    verify_table_clean(result, src)


def test_intelligent_defaults_to_text_when_table_vectors_overlap(tmp_path):
    src = make_table(tmp_path)
    result = process_pdf_intelligent(src, {0: [TABLE_RECT]})
    assert result.method == 'intelligent_text'
    verify_table_clean(result, src)


def test_universal_mode_rejects_crossing_table_borders(tmp_path):
    src = make_table(tmp_path)
    with pytest.raises(EditError, match='überschneiden den Rand'):
        process_pdf_universal(src, {0: [TABLE_RECT]})


def test_text_only_rejects_selection_without_selectable_text(tmp_path):
    src = make_table(tmp_path)
    with pytest.raises(EditError, match='Kein auswählbarer PDF-Text'):
        process_pdf_text_only(src, {0: [(541, 27, 587, 70)]})


def test_intelligent_falls_back_for_vector_only_selection(tmp_path):
    src = tmp_path / 'vector.pdf'
    d = pymupdf.open()
    p = d.new_page(width=400, height=240)
    p.draw_rect(pymupdf.Rect(100, 60, 140, 110))
    p.insert_text((200, 200), 'BLEIBT')
    d.save(src)
    d.close()
    result = process_pdf_intelligent(src, {0: [(90, 50, 150, 120)]})
    assert result.removed_vectors >= 1
    assert result.method in ('surgical', 'native')


def test_intelligent_rejects_mixed_text_and_nontext_rectangles(tmp_path):
    src = make_table(tmp_path)
    with pytest.raises(EditError, match='zwei Durchgängen'):
        process_pdf_intelligent(src, {0: [TABLE_RECT, (541, 27, 587, 70)]})


def test_rotated_page_selection_removes_only_text(tmp_path):
    src = make_table(tmp_path, rotated=True)
    with pymupdf.open(src) as before:
        selected = TABLE_RECT * before[0].rotation_matrix
    result = process_pdf_text_only(src, {0: [selected]})
    with pymupdf.open(stream=result.pdf_bytes, filetype='pdf') as clean:
        assert clean[0].rotation == 90
        assert 'VERTRAULICH' not in clean[0].get_text()
        assert 'BLEIBT' in clean[0].get_text()


def test_input_file_remains_unchanged(tmp_path):
    src = make_table(tmp_path)
    original = src.read_bytes()
    process_pdf_intelligent(src, {0: [TABLE_RECT]})
    assert src.read_bytes() == original
