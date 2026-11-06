"""Test real v1.0 modal checkboxes without manual clicking."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import App
from match_pages import PageMatch
import pymupdf


def main():
    app=App()
    try:
        app.update()
        matches=[PageMatch(1,pymupdf.Rect(5,5,15,15),'Identisches eingebettetes Bild',1.0),
                 PageMatch(2,pymupdf.Rect(5,5,15,15),'Identisches eingebettetes Bild',1.0)]
        def interact():
            dialogs=[c for c in app.winfo_children() if isinstance(c,tk.Toplevel)]
            assert len(dialogs)==1
            dlg=dialogs[0]
            # Test that each page has an independently controlled checkbox.
            def walk(node):
                yield node
                for child in node.winfo_children():yield from walk(child)
            buttons=[c for c in walk(dlg) if isinstance(c,tk.Checkbutton)]
            assert len(buttons)==2
            buttons[1].invoke()  # deselect page 3
            confirm=[c for c in walk(dlg) if isinstance(c,tk.Button) and c['text'] in ('Auswahl übernehmen','Apply selection')]
            assert len(confirm)==1
            confirm[0].invoke()
        app.after(200,interact)
        chosen=app._pick_page_matches(matches,True)
        assert [x.page_index for x in chosen]==[1]
        print('PASS: actual page checkboxes, independent selection, confirm action')
    finally:
        app.on_close()

if __name__=='__main__':main()
