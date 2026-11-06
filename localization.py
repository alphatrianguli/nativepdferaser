"""German/English interface strings for Native PDF Eraser.

The program's original interface was authored in German.  Translation is
presentation-only; PDF object handling and preservation logic are unaffected.
"""
from __future__ import annotations
import re

DE_EN = {
    # Initial status and common engine errors
    "PDF öffnen und Bereiche zum Entfernen markieren.": "Open a PDF and select areas to remove.",
    "Es werden nur PDF-Dateien unterstützt.": "Only PDF files are supported.",
    "Bitte vor der Verarbeitung mindestens ein Rechteck markieren.": "Select at least one rectangle before processing.",
    "Bitte mindestens ein Rechteck markieren.": "Select at least one rectangle.",
    "Bitte mindestens einen Bereich auswählen.": "Select at least one area.",
    "Keine gültigen Markierungen vorhanden.": "No valid selections found.",
    "Keine unterstützten PDF-Inhalte erkannt.": "No supported PDF content detected.",
    "Keine eingebetteten Bildlogos erkannt.": "No embedded image logos detected.",
    "Die Anzahl der Seiten wurde verändert.": "The page count changed.",
    "Seitenzahl wurde verändert.": "The page count changed.",
    "Standard-Metadaten wurden verändert.": "Standard metadata changed.",
    "Metadaten wurden verändert.": "Metadata changed.",
    "XMP/XML-Metadaten wurden verändert.": "XMP/XML metadata changed.",
    "Lesezeichen wurden verändert.": "Bookmarks changed.",
    "PDF-Ebenen wurden verändert.": "PDF layers changed.",
    "PDF-Links wurden verändert.": "PDF links changed.",
    "PDF-Anmerkungen wurden verändert.": "PDF annotations changed.",
    "Eingebettete Dateien wurden verändert.": "Embedded files changed.",
    "Das ursprüngliche Bild ist noch im Dokument referenziert.": "The original image is still referenced in the PDF.",
    "Verschlüsselte oder passwortgeschützte PDFs werden in Version 0.5 nicht unterstützt.": "Encrypted or password-protected PDFs are not supported.",
    "Digital signierte PDFs werden nicht unterstützt. Durch Bearbeitung erlischt die Signatur.": "Digitally signed PDFs are not supported: editing invalidates the signature.",
    # Menus & navigation
    "PDF öffnen...": "Open PDF...", "PDF öffnen": "Open PDF",
    "Geprüfte PDF speichern unter...": "Save verified PDF as...",
    "Beenden": "Exit", "Datei": "File", "Bearbeiten": "Edit",
    "Letztes Rechteck rückgängig": "Undo last rectangle",
    "Rechtecke auf Seite löschen": "Clear rectangles on page",
    "Alle Rechtecke löschen": "Clear all rectangles",
    "Letzte Entfernung rückgängig": "Undo last removal",
    "Zum Anfang / Zurücksetzen": "Back to start / Reset",
    "Über das Programm und Einschränkungen": "About and limitations",
    "Hilfe": "Help", "Inhalte präzise entfernen": "Precisely remove PDF content",
    "↶  Zurücksetzen": "↶  Reset", "Seite – / –": "Page – / –",
    "Anpassen": "Fit", "Seite einpassen": "Fit page",
    "▧  Bereich markieren": "▧  Select area", "✥  Verschieben": "✥  Pan",
    "Bereit": "Ready", "PDF öffnen, um zu starten": "Open a PDF to start",
    # Main workflow
    "Bildlogo erfassen": "Detect image logo",
    "Seiten abgleichen": "Find on other pages",
    "3 · BEARBEITEN": "3 · REMOVE",
    "Inhalt entfernen & prüfen": "Remove content & verify",
    "Noch keine Vorschau.": "No preview yet.",
    "Original": "Original", "Vorschau": "Preview",
    "4 · SPEICHERN": "4 · SAVE",
    "Original-PDF bleibt erhalten.": "Original PDF is preserved.",
    "1 · Entfernen": "1 · Remove", "1 · ENTFERNEN": "1 · REMOVE", "Rechteck um den gewünschten Inhalt ziehen.": "Draw a rectangle around content to remove.",
    "Modus": "Mode", "Intelligent (empfohlen)": "Intelligent (recommended)",
    "Nur Text": "Text only", "Nur Bilder": "Images only",
    "Alles entfernen": "Remove everything", "Nur Vektorgrafik": "Vector graphics only",
    "Objekte automatisch erkennen": "Automatically detect objects",
    "Andere Seiten automatisch prüfen": "Automatically check other pages",
    "2 · Markierungen": "2 · Selections", "2 · MARKIERUNGEN": "2 · SELECTIONS",
    "Entfernen": "Remove", "Rückgängig": "Undo", "Alle löschen": "Clear all",
    "Noch keine Markierung.": "No selection yet.",
    # Dialogs and notifications
    "PDF auswählen": "Choose PDF", "PDF-Dateien": "PDF files", "Alle Dateien": "All files",
    "PDF kann nicht geöffnet werden": "Cannot open PDF",
    "Seite konnte nicht angezeigt werden": "Cannot display page",
    "Keine frühere Entfernung": "No previous removal",
    "Es gibt keinen bearbeiteten Schritt zum Rückgängigmachen.": "There is no completed removal to undo.",
    "Letzte Entfernung rückgängig?": "Undo last removal?",
    "Der letzte geprüfte Entfernungsschritt wird verworfen.": "The last verified removal will be discarded.",
    "Letzte Entfernung rückgängig gemacht.": "Last removal undone.",
    "Neue Markierung: bitte entfernen & prüfen.": "New selection: please remove and verify.",
    "Keine Auswahl": "Nothing selected",
    "Bitte zuerst über dem Logo ein Rechteck ziehen.": "First draw a rectangle around the logo.",
    "Rechteck wählen": "Select a rectangle",
    "Bitte einen Eintrag in der Liste auswählen.": "Select an item from the list.",
    "Kein eindeutig erfasstes Bildlogo": "No matching image logo found",
    "Innerhalb des Rechtecks wurde kein ausreichend markiertes Bildlogo erkannt. Bitte das Logo zu mindestens etwa 55 % überdecken. Falls es aus Vektoren oder PDF-Text besteht, einen anderen Entfernungsmodus verwenden.":
    "No image logo was confidently detected in the rectangle. Cover at least about 55% of the logo, or choose another removal mode for vector/text logos.",
    "Mehrere Bilder gefunden": "Multiple images found",
    "Gleiche Elemente auf weiteren Seiten": "Matching elements on other pages",
    "Nur bestätigte Seiten werden markiert. Bitte die Treffer prüfen.": "Only confirmed pages will be selected. Please review the matches.",
    "Alle wählen": "Select all", "Keine wählen": "Select none",
    "Nur diese Seite": "Only this page", "Auswahl übernehmen": "Apply selection",
    "Seitensuche nicht möglich": "Page matching unavailable",
    "Keine weiteren Treffer": "No additional matches",
    "Keine identischen Inhalte an derselben Position auf anderen Seiten gefunden.": "No matching content was found at the same location on other pages.",
    "Weitere Seiten nicht markiert; aktuelle Auswahl bleibt erhalten.": "Other pages not selected; current selection remains.",
    "Bearbeitung zurücksetzen?": "Reset editing session?",
    "ALLE bisher vorgenommenen Entfernungen und Markierungen verwerfen?\nDie Original-PDF bleibt unverändert.":
    "Discard ALL completed removals and selections?\nThe original PDF will remain unchanged.",
    "Zurückgesetzt. Original geöffnet.": "Reset complete. Original PDF opened.",
    "Automatik: Bildlogos an Objektgrenzen erkennen; sonst Text oder Vektorgrafik entfernen.":
    "Automatic: detect image-logo bounds or remove selected text/vector content.",
    "Nur PDF-Text wird entfernt; Tabellen, Linien und Bilder bleiben bestehen.":
    "Only PDF text is removed; tables, lines and images are preserved.",
    "Bildobjekte werden anhand ihrer tatsächlichen Grenzen entfernt.":
    "Image objects are removed using their actual boundaries.",
    "Alle unterstützten Inhalte werden entfernt.": "All supported content types are removed.",
    "Nur vollständig eingeschlossene Vektoren werden entfernt.": "Only fully enclosed vector paths are removed.",
    "Entfernungsmodus gewählt.": "Removal mode selected.",
    "Keine bereinigte Vorschau": "No cleaned preview",
    "Bitte zuerst auf 'Inhalt entfernen & prüfen' klicken.": "First click 'Remove content & verify'.",
    "Bereinigte PDF wird angezeigt": "Showing cleaned PDF",
    "Original-PDF wird angezeigt": "Showing original PDF",
    "Bitte zuerst eine PDF öffnen und einen Bereich markieren.": "Open a PDF and draw a rectangle first.",
    "Keine Markierung": "No selection",
    "Bitte zuerst ein Rechteck über dem Logo zeichnen.": "Draw a rectangle around the content first.",
    "Bildbereich erweitern?": "Expand image selection?",
    "Der gesamte Bildinhalt wird entfernt.": "The full image content will be removed.",
    "Abgebrochen. Markierungen unverändert.": "Cancelled. Selections are unchanged.",
    "Entfernen und prüfen...": "Removing and verifying...",
    "GEPRÜFT. Sie können sofort den nächsten Bereich markieren oder speichern.":
    "VERIFIED. You can select the next area or save now.",
    "Keine Ausgabe erzeugt — Auswahl oder Prüfung fehlgeschlagen.":
    "No output produced — selection or verification failed.",
    "Prüfung nicht bestanden. Es wurde keine Ausgabe gespeichert.":
    "Verification failed. Nothing was saved.",
    "Entfernung konnte nicht verifiziert werden": "Removal could not be verified",
    "Verarbeitung fehlgeschlagen. Es wurde keine Ausgabe gespeichert.":
    "Processing failed. Nothing was saved.",
    "Verarbeitungsfehler": "Processing error", "Nichts zu speichern": "Nothing to save",
    "Bitte zuerst entfernen und prüfen.": "Run removal and verification first.",
    "Ungeprüfte Markierungen": "Unverified selections",
    "Bitte die neuen Markierungen zuerst mit 'Inhalt entfernen & prüfen' bearbeiten oder die Markierungen löschen, bevor Sie speichern.":
    "Process new selections with 'Remove content & verify' or clear them before saving.",
    "Geprüfte PDF speichern unter": "Save verified PDF as",
    "Bitte einen NEUEN Dateinamen wählen: Die Original-PDF muss unverändert bleiben.":
    "Choose a NEW file name: the original PDF must remain untouched.",
    "Die gespeicherte PDF stimmt nicht mit den verifizierten Daten überein.":
    "The saved PDF does not match the verified data.",
    "Speichern fehlgeschlagen": "Save failed", "PDF gespeichert": "PDF saved",
    "Die Original-PDF bleibt unverändert.": "The original PDF remains unchanged.",
    "Identischer PDF-Text": "Identical PDF text",
    "Identisches eingebettetes Bild": "Identical embedded image",
    "Sehr ähnliches Vektormuster": "Very similar vector pattern",
    "Bildlogo": "Image logo", "Bild und Text": "Image and text",
    "Vektorgrafik": "Vector graphic", "Text": "Text", "Manueller Bereich": "Manual selection",
}


def translate(message: str, lang: str = 'en') -> str:
    if lang != 'en':
        return message
    if message in DE_EN:
        return DE_EN[message]
    # Runtime labels containing values extracted from the document.
    m = re.fullmatch(r'Seite (\d+) / (\d+)', message)
    if m: return f'Page {m[1]} / {m[2]}'
    m = re.fullmatch(r'(\d+) markierte Bereiche', message)
    if m: return f'{m[1]} selected areas'
    m = re.fullmatch(r'(\d+) mögliche Übereinstimmung\(en\)', message)
    if m: return f'{m[1]} possible matches'
    m = re.fullmatch(r'Seite (\d+)\s+·\s+(.+)', message)
    if m: return f'Page {m[1]}  ·  {translate(m[2], lang)}'
    if message.startswith('Geöffnet: '): return message.replace('Geöffnet: ', 'Opened: ', 1).replace(' Seite(n)', ' page(s)')
    if message.startswith('Geprüfte Kopie gespeichert: '): return message.replace('Geprüfte Kopie gespeichert: ', 'Verified copy saved: ', 1)
    if message.startswith('Gespeichert:\n'): return message.replace('Gespeichert:\n', 'Saved:\n', 1).replace('Die Original-PDF bleibt unverändert.', 'The original PDF remains unchanged.')
    if message.startswith('Das Dokument wurde nicht gespeichert.'): return message.replace('Das Dokument wurde nicht gespeichert.', 'The document was not saved.',1)
    if message.startswith('✓ Geprüft'): return message.replace('✓ Geprüft', '✓ Verified', 1).replace('Entfernungsschritt(e) gespeichert','removal step(s) saved')
    if message.startswith('✓ Schritt '): return message.replace('✓ Schritt ', '✓ Step ', 1).replace(' Zeichen · ', ' chars · ').replace(' Bilder · ', ' images · ').replace(' Vektoren',' vectors')
    if message.startswith('Markierung auf die exakte Bildgrenze angepasst'): return message.replace('Markierung auf die exakte Bildgrenze angepasst', 'Selection snapped to precise image bounds',1).replace('Bildobjekt(e)', 'image object(s)')
    if message.startswith('Weitere Seiten'): return message.replace('Weitere Seiten','Other pages',1)
    if message.startswith('Bereiche gesamt'): return message.replace('Bereiche gesamt','areas total',1)
    if ' Bereiche gesamt ' in message: return message.replace(' Bereiche gesamt',' total areas',1).replace('Bilder:', 'Images:')
    if message.startswith('Bildgrenzen auf Seite(n) '): return message.replace('Bildgrenzen auf Seite(n)', 'Use complete image bounds on page(s)',1).replace(' vollständig übernehmen?', '?')
    if message.startswith('Es wurden ') and ' Bildobjekte erkannt' in message: return message.replace('Es wurden ', '',1).replace(' Bildobjekte erkannt. Alle Bildgrenzen erfassen?', ' image objects detected. Snap to all image bounds?')
    if message.startswith('Markierung'): return message
    m = re.fullmatch(r'(.+?) markiert\. (\d+) Vektorpfade, (\d+) Textwörter, (\d+) Bild\(er\)\.', message)
    if m: return f"{translate(m[1], lang)} selected. {m[2]} vector paths, {m[3]} text words, {m[4]} image(s)."
    m = re.fullmatch(r'(\d+) bestätigte Übereinstimmung\(en\) markiert: Seite\(n\) (.+)\.', message)
    if m: return f"{m[1]} confirmed matches selected on page(s) {m[2]}."
    if message.startswith('Seite '):
        m = re.match(r'Seite (\d+): (.*)', message)
        if m:
            return f'Page {m[1]}: {translate(m[2], lang)}'
    if message.startswith('Gespeichert:'): return message.replace('Gespeichert:','Saved:',1)
    return message
