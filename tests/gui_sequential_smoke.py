"""GUI regression: remove image, clear rectangles, draw text box, remove text, save both."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App, PAD, VERSION
from test_smart_mixed import make_mixed


def main():
    assert VERSION=='1.0'
    with TemporaryDirectory() as root:
        src=Path(root)/'example.pdf'
        output=Path(root)/'finished.pdf'
        make_mixed(src)
        with pymupdf.open(src) as original:
            origin_md=original.metadata
            original_image_count=len(original[0].get_image_info(xrefs=True))
        app=App()
        try:
            app.update()
            app.open_pdf(str(src))
            app.update()
            # Rough mouse selection should auto-expand to the true image bounds.
            def loc(x,y):
                return SimpleNamespace(x=int(PAD + x * app.zoom),y=int(PAD + y * app.zoom))
            start=loc(72,371);end=loc(140,403)
            app.canvas_press(start);app.canvas_move(end);app.canvas_release(end)
            assert app.auto_detect.get()
            assert app.selections[0][0].width > 68
            app.process()
            assert app.preview and app.result and app.save_btn['state']=='normal'
            assert not any(app.selections.values()), 'Rectangles should clear after first removal'
            first_step=app.result.pdf_bytes
            assert len(app._history_paths)==2
            # Draw a SECOND rectangle after completion -- should immediately
            # promote the verified candidate and allow new selections.
            start=loc(220,328);end=loc(358,347)
            app.canvas_press(start)
            assert not app.preview and app.preview_doc is None
            app.canvas_move(end)
            app.canvas_release(end)
            assert len(app.selections[0])==1
            assert app.save_btn['state']=='disabled', 'Save must block pending edits'
            # Ctrl+S should likewise refuse to save incomplete work.
            with patch('tkinter.messagebox.showwarning') as warning:
                app.save_as()
                warning.assert_called_once()
            app.process()
            assert app.result and not any(app.selections.values())
            assert len(app._history_paths)==3
            assert app.result.pdf_bytes!=first_step
            assert app.save_btn['state']=='normal'
            with pymupdf.open(stream=app.result.pdf_bytes,filetype='pdf') as final:
                assert not final[0].get_image_info(xrefs=True)
                assert 'Example Works GmbH' not in final[0].get_text()
                assert 'BLEIBT' in final[0].get_text()
                assert final.metadata == origin_md
            with patch('tkinter.filedialog.asksaveasfilename',return_value=str(output)):
                with patch('tkinter.messagebox.showinfo'):
                    app.save_as()
            assert output.read_bytes()==app.result.pdf_bytes
            # undo stage 2 -> stage 1 remains removed
            with patch('tkinter.messagebox.askyesno',return_value=True):
                app.undo_last_removal()
            assert len(app._history_paths)==2
            assert app.result.pdf_bytes==first_step
            with pymupdf.open(stream=app.result.pdf_bytes,filetype='pdf') as stage1:
                assert len(stage1[0].get_image_info(xrefs=True))<original_image_count
                assert 'Example Works GmbH' in stage1[0].get_text()
            with patch('tkinter.messagebox.askyesno',return_value=True):
                app.reset_to_start()
            assert not app.result and len(app._history_paths)==1
            print('PASS: sequential deletion, clear selections, save cumulative, undo stage, reset original')
        finally:
            app.on_close()

if __name__=='__main__': main()
