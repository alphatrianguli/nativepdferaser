"""v0.7 regressions: partial mouse selection, repeated image, crossing table lines."""
from pathlib import Path
import sys
import pytest
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_image_batch import create_doc
from engine import EditError, _verify_visual_page
from image_selection import image_candidates, snap_image_selections
from match_pages import discover_same_area_matches
from image_only import process_pdf_image_only
from text_only import process_pdf_intelligent

# The actual image is at x=100..190, y=100..155. Deliberately omit its edges.
ROUGH = pymupdf.Rect(108, 105, 182, 149)


def test_partial_rectangle_snaps_to_image_object_and_finds_other_pages(tmp_path):
    src=tmp_path/'cad_image.pdf'
    create_doc(src)
    with pymupdf.open(src) as orig:
        assert len(image_candidates(orig[0], ROUGH)) == 1
        snapped,_ = snap_image_selections(orig, {0:[ROUGH]})
        assert snapped[0][0] == orig[0].get_image_info(xrefs=True)[0]['bbox']
        matches = discover_same_area_matches(orig,0,ROUGH)
        assert [m.page_index for m in matches] == [1,2]
        rects = {0:[ROUGH], **{m.page_index:[m.rect] for m in matches}}
    result=process_pdf_intelligent(src,rects)
    assert result.modified_images == 3
    with pymupdf.open(src) as before, pymupdf.open(stream=result.pdf_bytes,filetype='pdf') as after:
        for p in range(3):
            assert before[p].get_drawings()==after[p].get_drawings()
            assert before[p].get_text('text')==after[p].get_text('text')
            assert not after[p].get_image_info(xrefs=True)
            image_bbox=pymupdf.Rect(before[p].get_image_info(xrefs=True)[0]['bbox'])
            for scale in (1,2):
                _verify_visual_page(before[p],after[p],[image_bbox],scale)


def test_a_stripe_across_image_is_not_taken_as_whole_logo(tmp_path):
    src=tmp_path/'cad_image.pdf'
    create_doc(src)
    with pymupdf.open(src) as original:
        assert image_candidates(original[0],(110,118,182,130))==[]
    with pytest.raises(EditError,match='nicht vollständig'):
        process_pdf_image_only(src,{0:[(110,118,182,130)]})


def test_shared_resource_requires_all_occurrences_even_with_partial_rectangle(tmp_path):
    src=tmp_path/'cad_image.pdf'
    create_doc(src)
    with pytest.raises(EditError,match='Bitte zuerst'):
        process_pdf_image_only(src,{0:[ROUGH]})
