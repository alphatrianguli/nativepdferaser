"""GUI v1.0: automatic page discovery with individual approval, no silent deletions."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App, PAD, VERSION
from test_image_batch import create_doc
from test_repeat_match import make_repeated_text


def choose(app, box):
    def mouse_point(x,y):
        return SimpleNamespace(x=int(PAD+x*app.zoom), y=int(PAD+y*app.zoom))
    start=mouse_point(box[0],box[1]); end=mouse_point(box[2],box[3])
    app.canvas_press(start);app.canvas_move(end);app.canvas_release(end)


def main():
    assert VERSION=='1.0'
    with TemporaryDirectory() as root:
        src=Path(root)/'three_images.pdf';create_doc(src)
        app=App()
        try:
            app.update();app.open_pdf(str(src));app.update()
            assert app.auto_find_pages.get() is True
            # Automatic popup picks page 2 only; page 3 is not silently edited.
            with patch.object(app,'_pick_page_matches',side_effect=lambda hits,automatic: [hits[0]]) as choice:
                choose(app,(105,103,184,150))
                choice.assert_called_once()
                assert choice.call_args.args[1] is True
            assert set(app.selections)=={0,1}
            # No selection confirmation -> only source page remains.
            app.clear_all()
            with patch.object(app,'_pick_page_matches',return_value=[]) as choice:
                choose(app,(105,103,184,150))
                choice.assert_called_once()
            assert set(k for k,v in app.selections.items() if v)=={0}
            app.clear_all()
            # Auto-discovery can be disabled without breaking manual selection.
            app.auto_find_pages.set(False)
            with patch.object(app,'_pick_page_matches') as chooser:
                choose(app,(105,103,184,150))
                chooser.assert_not_called()
            app.clear_all()
            app.auto_find_pages.set(True)
            # All matches, then end-to-end native image removal.
            with patch.object(app,'_pick_page_matches',side_effect=lambda hits,automatic: hits):
                choose(app,(105,103,184,150))
            assert set(app.selections)=={0,1,2}
            app.process()
            assert app.result and app.result.modified_images==3
            assert not any(app.selections.values())
            print('PASS: image matching dialog, individual approval, opt-out, all-pages image removal')
        finally:
            app.on_close()
        text=Path(root)/'repeated_text.pdf';make_repeated_text(text)
        app=App()
        try:
            app.update();app.open_pdf(str(text));app.update()
            with patch.object(app,'_pick_page_matches',side_effect=lambda hits,automatic:hits):
                choose(app,(208,298,345,324))
            assert set(app.selections)=={0,1,2}
            app.process()
            assert app.result and app.result.removed_text_chars>0
            with pymupdf.open(stream=app.result.pdf_bytes,filetype='pdf') as d:
                assert 'Example Works GmbH' not in d[0].get_text()
                assert 'Example Works GmbH' not in d[1].get_text()
                assert 'Example Works GmbH' not in d[2].get_text()
                assert 'Andere Firma GmbH' in d[3].get_text()
            print('PASS: repeated PDF text all-pages match, safe removal, different company retained')
        finally:
            app.on_close()

if __name__=='__main__': main()
