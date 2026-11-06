"""Validate live English/German toggle and application branding."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import App, APP_TITLE


def main():
    app = App()
    try:
        app.update()
        assert APP_TITLE == 'Native PDF Eraser'
        assert app.lang == 'en'
        assert app.language_combo.get() == 'English'
        assert app.reset_btn['text'].endswith('Reset')
        assert app.mode_combo.get() == 'Intelligent (recommended)'
        assert app.select_btn['text'].endswith('Select area')
        assert app.tr('PDF öffnen...') == 'Open PDF...'
        # The PDF canvas placeholder is not a Tk Label; verify its actual text.
        placeholder = lambda: [app.canvas.itemcget(i, 'text') for i in app.canvas.find_all()
                               if app.canvas.type(i) == 'text']
        assert 'Open a PDF to start' in placeholder(), placeholder()
        app.language_display.set('Deutsch')
        app.change_language()
        app.update()
        assert app.lang == 'de'
        assert app.reset_btn['text'].endswith('Zurücksetzen')
        assert app.mode_combo.get() == 'Intelligent (empfohlen)'
        assert app.select_btn['text'].endswith('Bereich markieren')
        assert app.tr('PDF öffnen...') == 'PDF öffnen...'
        assert 'PDF öffnen, um zu starten' in placeholder(), placeholder()
        app.removal_mode.set('text_only')
        app.on_removal_mode_change()
        assert app.mode_combo.get() == 'Nur Text'
        app.language_display.set('English')
        app.change_language()
        app.update()
        assert app.lang == 'en'
        assert app.mode_combo.get() == 'Text only'
        assert app.removal_mode.get() == 'text_only'
        assert app.reset_btn['text'].endswith('Reset')
        assert 'Open a PDF to start' in placeholder(), placeholder()
        print('PASS: bilingual interface and live-translated empty document placeholder')
    finally:
        app.on_close()


if __name__ == '__main__': main()
