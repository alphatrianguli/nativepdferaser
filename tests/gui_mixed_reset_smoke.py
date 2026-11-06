"""GUI regression: same-click text + embedded logo, then reset to step one."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App, VERSION
from test_smart_mixed import make_mixed


def main():
    with TemporaryDirectory() as root:
        src=Path(root)/'mixed.pdf'
        make_mixed(src)
        app=App()
        try:
            app.update()
            app.open_pdf(str(src))
            app.update()
            assert VERSION == '1.0'
            assert app.mode_combo.get() == 'Intelligent (recommended)'
            assert app.reset_btn['text'].endswith('Reset')
            app.selections={0:[pymupdf.Rect(64,365,145,410),pymupdf.Rect(220,328,358,347)]}
            app.render_page()
            app.process()
            assert app.result and app.result.method == 'smart_mixed'
            assert app.result.removed_text_chars > 0
            assert app.result.modified_images == 1
            assert app.save_btn['state']=='normal'
            with patch('tkinter.messagebox.askyesno', return_value=True):
                app.reset_to_start()
            assert app.preview is False and app.preview_doc is None
            assert app.result is None and not app.selections
            assert app.page_idx == 0
            assert app.save_btn['state']=='disabled'
            assert app.removal_mode.get()=='intelligent'
            assert app.source_path==src
            print('PASS: v1.0 bilingual controls, combined image+text, reset to step one')
        finally:
            app.on_close()

if __name__=='__main__':
    main()
