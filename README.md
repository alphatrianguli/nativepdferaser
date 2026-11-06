> **v1.0.1 maintenance update:** Fixed the empty-document message so it displays in English or German and updates immediately when switching languages.

# Native PDF Eraser 1.0 — English / Deutsch

A free-to-build, source-available Windows PDF editing application based on **Python, Tkinter and PyMuPDF**. Its purpose is to remove selected PDF text, embedded images and vector content without flattening the entire page.

**Language / Sprache:** Use the dropdown on the upper toolbar to switch between **English** and **Deutsch**, immediately and without losing current edits. The public edition uses a neutral blue interface and has no company branding.

## Features / Funktionen

- Draw one or more rectangles over unwanted PDF content. Choose **Intelligent**, **Text only**, **Images only**, **Remove everything**, or **Vector graphics only**.
- Recognize suitable embedded images and compact vector objects and adjust selections to their bounds.
- Automatically suggest identical image logos, matching PDF text, and highly similar vector patterns at corresponding locations on other pages. You select the pages before removal.
- Remove further elements in successive steps, undo the last completed step, or reset the entire session.
- Save a separate verified PDF. Text, drawings, metadata, and content outside selected rectangles are checked for unintended differences.

## Use on Windows / Unter Windows starten

**Build a one-file executable:**
1. Install Python 3.11–3.13 on **the Windows build computer**.
2. Extract this ZIP, then double-click `Build_Windows_EXE.bat` (first build requires internet to install dependencies).
3. When it finishes, distribute `dist\Native-PDF-Eraser.exe`.
4. End users **do not need Python** or internet connectivity to run the resulting EXE.

**Run from source:** Extract the ZIP and double-click `Run_on_Windows.bat` (requires Python on that computer).

The distributed ZIP contains **source code plus a Windows build script**, *not* a precompiled Windows executable. PyInstaller cannot cross-compile a Windows binary in this Linux build environment; the Windows build must be tested on Windows.

## Typical workflow / Kurzanleitung

1. **Open PDF / PDF öffnen**
2. **Select an area / Bereich markieren** (the application may recognize the underlying object automatically)
3. **Review suggestions / Weitere Seiten prüfen** — accept or reject individual page matches
4. **Remove & verify / Entfernen & prüfen**
5. Repeat or **Save As / Speichern unter**

Keyboard shortcuts: `Ctrl+O` open, `Ctrl+S` save, `Ctrl+Z` undo rectangle, `Ctrl+Shift+Z` undo last completed removal, `Ctrl+R` reset.

## Limitations and privacy / Grenzen und Datenschutz

- The application **does not upload documents to a server**; all processing takes place on the user's device.
- The program intentionally refuses edits that cannot pass its checks; this is not a guarantee of perfect preservation for every possible PDF structure.
- It cannot reliably erase every kind of nested object, clipped vector path, scanned/outlined text or differently positioned and resized graphic.
- Some embedded images are shared across pages. Removing only a subset of occurrences may be rejected. Confirm all proposed page matches carefully.
- **Original document metadata and unrelated content are preserved**, so documents may still contain identifying information in metadata, annotations, hidden layers, unused resources or attachments. This is **not** an automated whole-document anonymizer. Review the final PDF before sharing.
- Editing digitally signed PDFs invalidates signatures; encrypted/interactive documents may not be supported.
- Always have permission to modify and redistribute the PDF itself.

## Development / Entwicklung

Install dependencies and run engine tests:

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests
```

The GUI smoke tests are in `tests/gui_*smoke.py` and require Windows or Linux/Xvfb. The one-file Windows EXE build has not yet been validated in this environment.

## Open-source licensing / Lizenz

This source project is shared under **AGPL-3.0-or-later**, matching the AGPL licensing option for the PyMuPDF runtime. PyMuPDF is dual-licensed under AGPL or a commercial agreement; distributing a public compiled application brings additional legal obligations. Pillow and PyInstaller have separate licenses. See **`LICENSING.md`**, include the corresponding source and all required license notices when redistributing, and check with a legal professional if needed.

The name **Native PDF Eraser** has not been checked for trademark or domain availability.
