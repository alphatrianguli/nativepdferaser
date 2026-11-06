"""v1.0 regression: repeated images, native text, and vector drawings."""
from pathlib import Path
import sys
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repeat_match import discover_repeated_elements, discover_same_text_matches
from test_image_batch import create_doc, RECT
from text_only import process_pdf_text_only, _drawing_signature
from image_only import process_pdf_image_only
from smart_mixed import process_pdf_smart_mixed


def make_repeated_text(path: Path):
    with pymupdf.open() as doc:
        for i in range(4):
            p=doc.new_page(width=600, height=420)
            p.draw_rect((70, 280, 555, 390),color=(0,0,0),width=.5)
            p.draw_line((70,335),(555,335),color=(0,0,0),width=.5)
            p.insert_text((215,319), 'Example Works GmbH' if i != 3 else 'Andere Firma GmbH',fontsize=12)
            p.insert_text((88,318), 'Kunde',fontsize=10)
            p.insert_text((85,365),f'Seite {i+1}',fontsize=10)
        doc.save(path)


def test_repeated_text_detected_and_other_company_rejected(tmp_path):
    src=tmp_path/'text.pdf';make_repeated_text(src)
    box=pymupdf.Rect(206,299,351,324)
    with pymupdf.open(src) as doc:
        matches=discover_repeated_elements(doc,0,box)
        assert [m.page_index for m in matches] == [1,2]
        assert all(m.reason=='Identischer PDF-Text' for m in matches)
    selections={0:[box], **{m.page_index:[m.rect] for m in matches}}
    result=process_pdf_text_only(src,selections)
    with pymupdf.open(stream=result.pdf_bytes,filetype='pdf') as clean, pymupdf.open(src) as orig:
        for i in range(3):
            assert 'Example Works GmbH' not in clean[i].get_text()
            assert clean[i].get_drawings()==orig[i].get_drawings()
        assert 'Andere Firma GmbH' in clean[3].get_text()


def test_short_page_labels_never_auto_match(tmp_path):
    src=tmp_path/'text.pdf';make_repeated_text(src)
    with pymupdf.open(src) as doc:
        assert not discover_same_text_matches(doc,0,(83,345,115,366))


def test_same_image_content_match_all_pages(tmp_path):
    src=tmp_path/'img.pdf';create_doc(src)
    with pymupdf.open(src) as doc:
        hits=discover_repeated_elements(doc,0,RECT)
        assert [h.page_index for h in hits]==[1,2]
        assert all(h.reason=='Identisches eingebettetes Bild' for h in hits)
    result=process_pdf_image_only(src,{0:[RECT],**{m.page_index:[m.rect] for m in hits}})
    assert result.modified_images==3


def test_vector_content_match_same_position_without_text(tmp_path):
    src=tmp_path/'vectors.pdf'
    with pymupdf.open() as d:
        for idx in range(3):
            p=d.new_page(width=600,height=420)
            p.draw_rect((80,100,140,170),color=(0,0,0),width=2)
            if idx != 2:
                p.draw_circle((110,130),15,color=(0,0,0),fill=(0,0,0))
        d.save(src)
    with pymupdf.open(src) as d:
        m=discover_repeated_elements(d,0,(73,93,147,177))
        assert [x.page_index for x in m]==[1]


