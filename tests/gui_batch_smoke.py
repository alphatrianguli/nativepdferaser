"""End-to-end GUI smoke: one rectangle -> search -> three selected pages -> remove."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App
from test_image_batch import create_doc,RECT

def main():
    with TemporaryDirectory() as tmp:
        src=Path(tmp)/'image_logo.pdf'
        create_doc(src)
        app=App()
        try:
            app.update()
            app.open_pdf(str(src))
            app.update()
            app.selections={0:[RECT]}
            app.render_page()
            with patch.object(app, '_pick_page_matches', side_effect=lambda hits, automatic: hits):
                app.find_same_logo_pages()
            assert set(app.selections)=={0,1,2}
            assert all(len(v)==1 for v in app.selections.values())
            app.process()
            assert app.result is not None and app.result.method=='image_only'
            assert app.result.modified_images==3 and app.save_btn['state']=='normal'
            assert app.preview and app.preview_doc is not None
            print('PASS: GUI logo detection, batch selection, image removal and verification')
        finally:
            app.on_close()

if __name__=='__main__':
    main()
