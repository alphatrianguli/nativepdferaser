"""Xvfb/Windows smoke test: German UI, universal mode, text+image, Save As."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO

import pymupdf
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import App, APP_TITLE, VERSION
import main


def run():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "eingabe.pdf"
        output = root / "ausgabe_bereinigt.pdf"
        im = Image.new('RGB', (80, 50), 'white')
        dr = ImageDraw.Draw(im)
        dr.rectangle((10, 10, 68, 40), fill='#1564A7')
        buf = BytesIO()
        im.save(buf, format='PNG')
        doc = pymupdf.open()
        page = doc.new_page(width=560, height=330)
        page.insert_text((50, 40), 'BLEIBT UNVERAENDERT', fontsize=12)
        page.insert_text((50, 140), 'GEHEIM', fontsize=18)
        page.insert_image(pymupdf.Rect(300, 100, 380, 150), stream=buf.getvalue())
        doc.set_metadata({'author': 'Example Publisher', 'title': 'Pruefung'})
        doc.save(source)
        doc.close()
        app = App()
        old_save = main.filedialog.asksaveasfilename
        try:
            app.update()
            app.open_pdf(str(source))
            app.update()
            assert APP_TITLE == 'Native PDF Eraser'
            assert VERSION == '1.0'
            assert app.removal_mode.get() == 'intelligent'
            app.removal_mode.set('universal')
            app.on_removal_mode_change()
            assert 'Native PDF Eraser' in app.title()
            assert 'Native PDF Eraser' not in app.status_var.get()  # footer independent
            app.selections = {0: [pymupdf.Rect(45, 110, 150, 145),
                                  pymupdf.Rect(295, 95, 385, 155)]}
            app.undo_stack.clear()
            app.render_page()
            app.process()
            assert app.result is not None
            assert app.result.method == 'universal'
            assert app.result.removed_text_chars > 0
            assert app.result.modified_images == 1
            assert app.preview
            assert app.save_btn['state'] == 'normal'
            main.filedialog.asksaveasfilename = lambda **kwargs: str(output)
            # Avoid a modal pop-up in the headless test.
            old_info = main.messagebox.showinfo
            main.messagebox.showinfo = lambda *args, **kwargs: None
            try:
                app.save_as()
            finally:
                main.messagebox.showinfo = old_info
            assert output.exists()
            with pymupdf.open(output) as clean:
                assert 'GEHEIM' not in clean[0].get_text()
                assert 'BLEIBT' in clean[0].get_text()
                assert len(clean[0].get_image_info(xrefs=True)) == 0
                assert clean.metadata['author'] == 'Example Publisher'
            print('PASS: v0.5 German UI, universal text/image removal, preview, Save As')
        finally:
            main.filedialog.asksaveasfilename = old_save
            app.on_close()


if __name__ == '__main__':
    run()
