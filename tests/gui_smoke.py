"""End-to-end Tk app check; needs a working graphical display (Windows or Xvfb)."""
import sys
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory

import pymupdf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import App, PAD


def main():
    with TemporaryDirectory() as root:
        source = Path(root) / 'input.pdf'
        d = pymupdf.open()
        p = d.new_page(width=600, height=400)
        p.draw_rect(pymupdf.Rect(75, 80, 130, 135), color=(0, 0, 0), width=1)
        p.draw_line((15, 300), (560, 300), color=(0,0,0), width=0.2)
        p.insert_text((200, 120), 'KEEP TEXT', fontsize=15)
        d.set_metadata({'author': 'Metadata must stay'})
        d.save(source)
        d.close()
        app = App()
        try:
            app.update()
            app.open_pdf(str(source))
            app.update()
            # Exercise actual pixel-to-PDF rectangle selection events.
            rect = pymupdf.Rect(65, 70, 145, 150)
            def mouse_point(x, y):
                return SimpleNamespace(x=int(PAD + x*app.zoom), y=int(PAD + y*app.zoom))
            start = mouse_point(rect.x0, rect.y0)
            end = mouse_point(rect.x1, rect.y1)
            app.canvas_press(start)
            app.canvas_move(end)
            app.canvas_release(end)
            assert len(app.selections.get(0, [])) == 1
            app.process()
            assert app.result and app.result.removed_vectors > 0
            assert app.preview and app.save_btn['state'] == 'normal'
            assert app.result.metadata_preserved
            print('PASS: GUI open, drag selection, process, verify, preview, Save enabled')
        finally:
            app.on_close()


if __name__ == '__main__':
    main()
