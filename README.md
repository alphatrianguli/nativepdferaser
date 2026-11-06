# Native PDF Eraser v1.0.1 — English / Deutsch

**Native PDF Eraser** is a free, open-source Windows application for removing selected PDF text, embedded images and vector graphics without converting whole pages into images. It is built with **Python, Tkinter and PyMuPDF**.

**Language / Sprache:** Switch between **English** and **Deutsch** in the toolbar without restarting the application or losing your edits.

## Download for Windows / Download für Windows

**Ready-to-use Windows application — no Python installation or build required.**

1. Open the **[latest GitHub Release](https://github.com/alphatrianguli/nativepdferaser/releases/latest)**.
2. Under **Assets**, download **`Native-PDF-Eraser.exe`** (not *Source code (zip)*).
3. Save the EXE anywhere you like and double-click it to launch the application.
4. Open a PDF and start editing. No installer or additional Python packages are needed on the user's computer.

**Deutsch:** Öffne die **[neueste Version auf GitHub](https://github.com/alphatrianguli/nativepdferaser/releases/latest)**, lade unter **Assets** die Datei **`Native-PDF-Eraser.exe`** herunter und starte sie per Doppelklick. **Python muss nicht installiert werden.**

> **Security note / Sicherheitshinweis:** This portable EXE is currently unsigned, so Windows or antivirus software might display a warning. Download only from this project's GitHub Releases page, and review unexpected security alerts rather than disabling protection. / Die EXE ist derzeit nicht digital signiert. Lade sie nur von der offiziellen GitHub-Release-Seite herunter und prüfe unerwartete Sicherheitswarnungen.

## Features / Funktionen

- Select unwanted content by drawing rectangles on PDF pages.
- Choose **Intelligent**, **Text only**, **Images only**, **Remove everything** or **Vector graphics only**.
- Automatically identify supported embedded images and compact vector graphics to refine a selection.
- Suggest matching images, text or vector patterns on other pages; confirm which pages to edit.
- Remove several elements in successive steps, undo the last completed step, or reset to the original PDF.
- Save a separate PDF after checks for unintended changes to surrounding content, extracted text and metadata.

## How to use / Kurzanleitung

1. **Open PDF / PDF öffnen** — Choose your document.
2. **Select / Markieren** — Draw a rectangle around the element you want to remove.
3. **Review matches / Treffer prüfen** — Optionally confirm suggested matches on other pages.
4. **Remove & verify / Entfernen & prüfen** — Inspect the processed result.
5. **Repeat or Save As / Wiederholen oder Speichern unter** — Keep editing, or save a new PDF. The original is not overwritten.

Keyboard shortcuts: `Ctrl+O` open, `Ctrl+S` save, `Ctrl+Z` undo rectangle, `Ctrl+Shift+Z` undo the last completed removal, `Ctrl+R` reset.

## Build from source / Aus Quellcode erstellen

**Only developers need this section.** Users can download the ready-made EXE above.

To build the single-file Windows EXE yourself:

1. Download the repository source code or clone the repository.
2. Install Python 3.11–3.13 on the **Windows build computer**.
3. Run `Build_Windows_EXE.bat` (internet access is needed for the first dependency installation).
4. Find the executable at `dist\Native-PDF-Eraser.exe`.

Alternatively, run the Python source on Windows with `Run_on_Windows.bat` (requires Python).

### Run tests / Tests ausführen

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests
```

GitHub Actions can also build and attach the Windows EXE to a GitHub Release; see `.github/workflows/` in the repository. The packaged EXE has been built through the release workflow, but not every possible Windows configuration or PDF structure has been independently tested.

## Limitations and privacy / Grenzen und Datenschutz

- PDF files are processed on your computer; the application does not upload them to a server.
- Not all PDFs can be edited safely. The application intentionally rejects operations that fail its preservation checks.
- Some complex nested objects, clipped vector graphics, outlined/scanned text, or reused embedded images may require manual handling or cannot be safely removed.
- Visual comparison alone does **not** prove complete sanitization. Original metadata, attachments, hidden layers or unrelated company references may remain in the PDF.
- Modifying a digitally signed PDF generally invalidates its signature. Encrypted and interactive PDFs may not be supported.
- Always review the final PDF and ensure you have permission to modify and redistribute the document.

## License / Lizenz

This application is shared under **AGPL-3.0-or-later** and uses **PyMuPDF** (AGPL or commercial license). See [`LICENSING.md`](LICENSING.md) for licensing and redistribution information. When sharing compiled binaries, comply with applicable source-code and license-notice requirements.

The name **Native PDF Eraser** has not been checked for trademark or domain availability.
