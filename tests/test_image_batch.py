"""Regression cases for repeated image logos and same-position matching."""
from pathlib import Path
import io,sys
import pytest
import pymupdf
from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import EditError
from match_pages import discover_same_area_matches
from image_only import process_pdf_image_only
from text_only import process_pdf_intelligent

RECT=pymupdf.Rect(90,80,205,170)

def logo_data():
    im=Image.new('RGB',(150,80),'white')
    d=ImageDraw.Draw(im)
    d.polygon([(20,55),(75,5),(135,55)],fill='black')
    buffer=io.BytesIO()
    im.save(buffer,format='PNG')
    return buffer.getvalue()

def create_doc(path,extra_different_image=False,misplaced=False):
    logo=logo_data()
    with pymupdf.open() as d:
        for n in range(3):
            p=d.new_page(width=600,height=450)
            p.draw_rect((80,50,450,220),color=(0,0,0),width=0.55)
            p.draw_line((75,100),(560,100),color=(0,0,0),width=0.2)
            p.insert_text((225,125),f'TITLE PAGE {n+1}',fontsize=11)
            target=(100,100,190,155)
            if n==2 and misplaced: target=(300,300,390,355)
            p.insert_image(pymupdf.Rect(target),stream=logo)
            if extra_different_image and n==1:
                img2=Image.new('RGB',(80,50),(20,100,200))
                b=io.BytesIO();img2.save(b,format='PNG')
                p.insert_image((400,320,470,367),stream=b.getvalue())
        d.set_metadata({'title':'Keep metadata','author':'Test Manufacturing'})
        d.save(path)

def test_smart_match_repeated_logo_all_pages(tmp_path):
    src=tmp_path/'three.pdf';create_doc(src,extra_different_image=True)
    with pymupdf.open(src) as doc:
        assert len({im['digest'] for p in doc for im in p.get_image_info(xrefs=True) if im['bbox'][0]<250})==1
        matches=discover_same_area_matches(doc,0,RECT)
    assert [m.page_index for m in matches]==[1,2]
    assert all(m.confidence==1.0 for m in matches)
    rects={0:[RECT], **{m.page_index:[m.rect] for m in matches}}
    result=process_pdf_image_only(src,rects)
    assert result.method=='image_only' and result.modified_images==3
    assert result.edited_pages==3
    with pymupdf.open(src) as before,pymupdf.open(stream=result.pdf_bytes,filetype='pdf') as after:
        assert before.metadata==after.metadata
        for idx in range(3):
            assert before[idx].get_text('text')==after[idx].get_text('text')
            assert before[idx].get_drawings()==after[idx].get_drawings()
        assert len(after[0].get_image_info(xrefs=True))==0
        assert len(after[1].get_image_info(xrefs=True))==1 # unselected unrelated image
        assert len(after[2].get_image_info(xrefs=True))==0

def test_shared_logo_one_page_is_blocked(tmp_path):
    src=tmp_path/'three.pdf'; create_doc(src)
    with pytest.raises(EditError,match='alle Vorkommen|alle Vorkommen|Bitte zuerst'):
        process_pdf_image_only(src,{0:[RECT]})

def test_smart_match_does_not_guess_different_location(tmp_path):
    src=tmp_path/'three.pdf';create_doc(src,misplaced=True)
    with pymupdf.open(src) as doc:
        matches=discover_same_area_matches(doc,0,RECT)
    assert [m.page_index for m in matches]==[1]
    with pytest.raises(EditError,match='Bitte zuerst'):
        process_pdf_image_only(src,{0:[RECT],1:[RECT]})

def test_rejects_partially_selected_image(tmp_path):
    src=tmp_path/'three.pdf';create_doc(src)
    with pytest.raises(EditError,match='nicht vollständig'):
        process_pdf_image_only(src,{0:[(105,105,120,120)]})

def test_intelligent_prefers_image_over_crossing_table_path(tmp_path):
    src=tmp_path/'three.pdf';create_doc(src)
    with pymupdf.open(src) as d:
        matches=discover_same_area_matches(d,0,RECT)
    rects={0:[RECT],**{x.page_index:[x.rect] for x in matches}}
    result=process_pdf_intelligent(src,rects)
    assert result.method=='image_only'
    assert result.modified_images==3

def test_vector_pattern_recognition_at_same_position(tmp_path):
    src=tmp_path/'vector.pdf'
    with pymupdf.open() as d:
        for i in range(3):
            p=d.new_page(width=600,height=450)
            p.draw_rect((70,70,160,145),color=(0,0,0),width=2)
            if i!=2:
                p.draw_circle((110,106),20,color=(0,0,0),fill=(0,0,0))
            p.insert_text((300,300),f'Other {i}',fontsize=14)
        d.save(src)
    with pymupdf.open(src) as doc:
        matches=discover_same_area_matches(doc,0,(65,65,165,150))
    assert [m.page_index for m in matches]==[1]
