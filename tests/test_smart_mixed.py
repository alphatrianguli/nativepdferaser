"""Regression: image logo and selectable table text in one processing click."""
from pathlib import Path
import sys
from io import BytesIO
import pymupdf
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smart_mixed import process_pdf_smart_mixed, classify_selections
from engine import EditError
from text_only import _drawing_signature


def make_mixed(path, shared=False):
    img = Image.new('RGB', (70, 40), 'white')
    # black visible mark
    for x in range(10, 35):
        for y in range(6, 34):
            img.putpixel((x,y), (0,0,0))
    b=BytesIO(); img.save(b,format='PNG')
    with pymupdf.open() as doc:
        for i in range(2 if shared else 1):
            p=doc.new_page(width=600,height=450)
            p.draw_rect(pymupdf.Rect(40,300,560,420),color=(0,0,0),width=.5)
            p.draw_line((200,300),(200,420),color=(0,0,0),width=.5)
            p.draw_line((40,365),(560,365),color=(0,0,0),width=.5)
            p.insert_text((222,340),'Example Works GmbH',fontsize=12)
            p.insert_text((425,340),'BLEIBT',fontsize=12)
            p.insert_image(pymupdf.Rect(65,365,145,410),stream=b.getvalue())
        doc.set_metadata({'author':'Example Publisher','title':'mixed'})
        doc.save(path)


def test_mixed_table_text_image_same_page(tmp_path):
    src=tmp_path/'mix.pdf'; make_mixed(src)
    selections={0:[pymupdf.Rect(65,365,145,410), pymupdf.Rect(220,328,358,347)]}
    with pymupdf.open(src) as before:
        v_before=_drawing_signature(before[0]); meta=before.metadata
        image_count=len(before[0].get_image_info(xrefs=True))
    result=process_pdf_smart_mixed(src,selections)
    assert result.modified_images==1
    assert result.removed_text_chars>=len('Example Works GmbH')
    with pymupdf.open(stream=result.pdf_bytes,filetype='pdf') as doc:
        assert len(doc[0].get_image_info(xrefs=True))==image_count-1
        assert 'Example' not in doc[0].get_text()
        assert 'BLEIBT' in doc[0].get_text()
        assert _drawing_signature(doc[0])==v_before
        assert doc.metadata==meta


def test_mixed_image_and_text_in_single_rectangle(tmp_path):
    src=tmp_path/'mix.pdf'; make_mixed(src)
    # Overlap both image and neighboring table text in a wide rectangle.
    result=process_pdf_smart_mixed(src,{0:[pymupdf.Rect(63,324,370,412)]})
    assert result.modified_images==1
    assert result.removed_text_chars>0
    with pymupdf.open(stream=result.pdf_bytes,filetype='pdf') as doc:
        assert not doc[0].get_image_info(xrefs=True)
        assert 'Example' not in doc[0].get_text()
        assert 'BLEIBT' in doc[0].get_text()


def test_mixed_reused_image_requires_all_occurrences(tmp_path):
    src=tmp_path/'shared.pdf'; make_mixed(src,shared=True)
    with pytest.raises(EditError,match='markiert|Seite'):
        process_pdf_smart_mixed(src,{0:[pymupdf.Rect(65,365,145,410),pymupdf.Rect(220,328,358,347)]})
    rects={i:[pymupdf.Rect(65,365,145,410)] for i in (0,1)}
    rects[0].append(pymupdf.Rect(220,328,358,347))
    res=process_pdf_smart_mixed(src,rects)
    assert res.modified_images==2
    with pymupdf.open(stream=res.pdf_bytes,filetype='pdf') as doc:
        assert len(doc[0].get_image_info(xrefs=True))==0
        assert len(doc[1].get_image_info(xrefs=True))==0
        assert 'Example' not in doc[0].get_text()
        assert 'Example' in doc[1].get_text()
