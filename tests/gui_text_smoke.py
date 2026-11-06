"""GUI smoke test of automatic table-safe text removal and German controls."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import App, APP_TITLE, VERSION


def run():
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / 'tabelle.pdf'
        with pymupdf.open() as doc:
            page = doc.new_page(width=600, height=380)
            page.draw_line((50, 120), (530, 120), color=(0, 0, 0), width=0.4)
            page.draw_line((50, 180), (530, 180), color=(0, 0, 0), width=0.4)
            page.draw_line((220, 90), (220, 220), color=(0, 0, 0), width=0.4)
            page.insert_text((250, 145), 'VERTRAULICH', fontsize=16)
            page.insert_text((65, 145), 'BLEIBT', fontsize=16)
            doc.set_metadata({'author': 'Example Publisher'})
            doc.save(source)
        app = App()
        try:
            app.update()
            app.open_pdf(str(source))
            app.update()
            assert APP_TITLE == 'Native PDF Eraser'
            assert VERSION == '1.0'
            assert app.removal_mode.get() == 'intelligent'
            assert 'Native PDF Eraser' in app.title()
            app.selections = {0: [pymupdf.Rect(240, 126, 405, 153)]}
            app.render_page()
            app.process()
            assert app.result is not None
            assert app.result.method == 'intelligent_text'
            assert app.result.removed_text_chars == len('VERTRAULICH')
            assert app.preview
            assert app.save_btn['state'] == 'normal'
            with pymupdf.open(stream=app.result.pdf_bytes, filetype='pdf') as cleaned:
                assert 'VERTRAULICH' not in cleaned[0].get_text()
                assert 'BLEIBT' in cleaned[0].get_text()
                assert len(cleaned[0].get_drawings()) == 3
            # Switching mode keeps the last verified PDF and Save As available.
            app.removal_mode.set('text_only')
            app.on_removal_mode_change()
            assert app.save_btn['state'] == 'normal'
            print('PASS: v0.5 GUI intelligent table text removal and mode switching')
        finally:
            app.on_close()


if __name__ == '__main__':
    run()
