"""GUI smoke for v0.7: rough selection -> snap -> same image on all pages -> process."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App, VERSION
from test_image_batch import create_doc
from test_image_snap import ROUGH


def main():
    with TemporaryDirectory() as temp:
        source=Path(temp)/'sample.pdf'
        create_doc(source)
        app=App()
        try:
            app.update()
            app.open_pdf(str(source))
            app.update()
            assert VERSION == '1.0'
            app.selections={0:[ROUGH]}
            app.render_page()
            app.snap_selected_image()
            assert app.selections[0][0].width > ROUGH.width
            with patch.object(app, '_pick_page_matches', side_effect=lambda hits, automatic: hits):
                app.find_same_logo_pages()
            assert set(app.selections)=={0,1,2}
            app.process()
            assert app.result and app.result.modified_images == 3
            assert app.result.method == 'image_only' and app.save_btn['state'] == 'normal'
            print('PASS: v0.7 GUI rough image selection, exact snap, all-page match, remove and verify')
        finally:
            app.on_close()

if __name__=='__main__':
    main()
