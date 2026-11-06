"""Detection should snap image/vector content, not an entire table grid."""
from io import BytesIO
from pathlib import Path
import sys
import pymupdf
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from object_recognition import detect_object
from engine import inspect_selection


def test_snap_vector_logo_with_nearby_table(tmp_path):
    src=tmp_path/'vector_logo.pdf'
    with pymupdf.open() as d:
        p=d.new_page(width=600,height=400)
        p.draw_rect((40,40,570,360),color=(0,0,0),width=.4)
        p.draw_line((40,300),(570,300),color=(0,0,0),width=.4)
        # Build a compact logo from many little lines, as in CAD PDFs.
        for n in range(40):
            x=170 + n * .9
            p.draw_line((x,305+(n % 6)),(x+1.5,320+(n % 6)),color=(0,0,0),width=.4)
        d.save(src)
    with pymupdf.open(src) as d:
        initial=pymupdf.Rect(173,307,204,324)
        hit=detect_object(d[0],initial,'intelligent')
        assert hit.kind=='vector'
        assert hit.objects>=15
        assert hit.rect.width > initial.width
        assert hit.rect.y1 < 350  # never enlarge to whole bottom border
        assert hit.rect.x0 > 140


def test_snap_image_and_ignore_table_borders(tmp_path):
    src=tmp_path/'drawing.pdf'
    b=BytesIO()
    Image.new('RGB',(40,30), 'black').save(b,format='PNG')
    with pymupdf.open() as d:
        p=d.new_page(width=600,height=400)
        p.draw_rect((20,20,580,390),color=(0,0,0),width=.5)
        p.draw_rect((60,250,500,360),color=(0,0,0),width=.5)
        p.insert_image((90,275,160,330),stream=b.getvalue())
        d.save(src)
    with pymupdf.open(src) as d:
        hit=detect_object(d[0],pymupdf.Rect(95,280,155,323),'intelligent')
        assert hit.kind=='image'
        assert hit.rect == pymupdf.Rect(d[0].get_image_info(xrefs=True)[0]["bbox"])
        nothing=detect_object(d[0],pymupdf.Rect(62,260,85,287),'intelligent')
        assert nothing.kind!='vector'  # a touching table line is never snapped


def test_text_mode_preserves_exact_selection(tmp_path):
    src=tmp_path/'table.pdf'
    with pymupdf.open() as d:
        p=d.new_page(width=500,height=300)
        p.draw_rect((15,15,480,280),color=(0,0,0))
        p.insert_text((100,130),'KUNDENNAME',fontsize=12)
        d.save(src)
    with pymupdf.open(src) as d:
        selected=pymupdf.Rect(95,114,225,140)
        result=detect_object(d[0],selected,'intelligent')
        assert result.kind=='text'
        assert result.rect==selected
