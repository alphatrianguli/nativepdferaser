"""Native PDF Eraser v0.5: text-first, table-safe rectangle removal.

Text is removed using native PDF redaction while preserving drawings, images,
annotations, page size and document metadata. No white/redaction overlay is
placed. A non-incremental save discards orphaned text operators. Unsupported
or unexpectedly altered documents are rejected instead of being written.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pymupdf

from engine import (
    EditError, VerificationError, ProcessResult, _as_rect, _page_coords,
    _check_document, _verification_scales, _verify_visual_page,
)
from universal import (
    _text_outside, _text_inside_count, _text_chars, _links, _annotations,
    process_pdf_universal,
)


def _rectangles(doc: pymupdf.Document, selections: Mapping) -> dict[int, list[pymupdf.Rect]]:
    if not selections or not any(selections.values()):
        raise EditError("Bitte mindestens ein Rechteck markieren.")
    rects = {}
    for idx, values in selections.items():
        if not isinstance(idx, int) or not 0 <= idx < doc.page_count:
            raise EditError(f"Ungültige Seitennummer: {idx!r}")
        page = doc[idx]
        unrotated = []
        for value in values:
            display = _as_rect(value)
            if not page.rect.contains(display):
                raise EditError(f"Markierung außerhalb von Seite {idx + 1}.")
            unrotated.append(_page_coords(page, display))
        if unrotated:
            rects[idx] = unrotated
    if not rects:
        raise EditError("Keine gültigen Markierungen vorhanden.")
    return rects


def _drawing_signature(page: pymupdf.Page) -> Counter:
    """Conservative drawing signature; count plus pixel comparisons also checked."""
    def canonical(value):
        if isinstance(value, (float, int)):
            return round(float(value), 5)
        if isinstance(value, (list, tuple)):
            return tuple(canonical(v) for v in value)
        if isinstance(value, pymupdf.Point):
            return (round(value.x, 5), round(value.y, 5))
        if isinstance(value, pymupdf.Rect):
            return tuple(round(v, 5) for v in value)
        if isinstance(value, pymupdf.Quad):
            return tuple(canonical(v) for v in (value.ul, value.ur, value.ll, value.lr))
        return str(value)

    return Counter(
        (
            canonical(d.get("items")), canonical(d.get("rect")),
            canonical(d.get("color")), canonical(d.get("fill")),
            canonical(d.get("width")), canonical(d.get("closePath")),
            canonical(d.get("dashes")), canonical(d.get("lineCap")),
            canonical(d.get("lineJoin")), canonical(d.get("fill_opacity")),
            canonical(d.get("stroke_opacity")),
        )
        for d in page.get_drawings()
    )


def _image_signature(page: pymupdf.Page) -> Counter:
    return Counter(
        (info.get("digest"), tuple(round(float(v), 4) for v in info.get("bbox", ())),
         info.get("width"), info.get("height"))
        for info in page.get_image_info(xrefs=True)
    )


def process_pdf_text_only(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Delete actual text characters, including inside a crossing vector table grid."""
    def report(s):
        if progress:
            progress(s)

    source = Path(input_path)
    if not source.is_file():
        raise EditError(f"PDF-Datei nicht gefunden: {source}")

    with pymupdf.open(source) as original:
        _check_document(original)
        rects_by_page = _rectangles(original, selections)
        counts = {}
        for idx, rr in rects_by_page.items():
            n = _text_inside_count(original[idx], rr)
            if not n:
                raise EditError(
                    f"Seite {idx + 1}: Kein auswählbarer PDF-Text innerhalb der Markierung. "
                    "Für Vektor- oder Bildlogos bitte Universalmodus wählen."
                )
            counts[idx] = n

        orig_metadata = dict(original.metadata)
        orig_xmp = original.get_xml_metadata()
        orig_toc = original.get_toc(simple=True)
        orig_embedded = original.embfile_count()
        orig_ocgs = sorted((v.get("name"), v.get("on"), str(v.get("intent")))
                           for v in original.get_ocgs().values())
        orig_links = {i: _links(original[i]) for i in range(original.page_count)}
        orig_annots = {i: _annotations(original[i]) for i in range(original.page_count)}
        original_vectors = {idx: _drawing_signature(original[idx]) for idx in rects_by_page}
        original_images = {idx: _image_signature(original[idx]) for idx in rects_by_page}
        original_outside = {idx: _text_outside(original[idx], rr) for idx, rr in rects_by_page.items()}

        with pymupdf.open(source) as edited:
            for idx, rr in rects_by_page.items():
                page = edited[idx]
                report(f"Seite {idx + 1}: entferne nur Text (Tabellenlinien bleiben erhalten)...")
                for r in rr:
                    page.add_redact_annot(r, fill=False, cross_out=False)
                page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
            edited.set_metadata({k: v for k, v in orig_metadata.items()
                                 if k not in ("format", "encryption")})
            if orig_xmp and edited.get_xml_metadata() != orig_xmp:
                edited.set_xml_metadata(orig_xmp)
            output = edited.tobytes(
                garbage=4, deflate=True, deflate_images=True, clean=False,
                no_new_id=True, encryption=pymupdf.PDF_ENCRYPT_NONE,
            )

        report("Prüfe Textentfernung, Grafiken, Bilder und Dokumentstruktur...")
        with pymupdf.open(stream=output, filetype="pdf") as candidate:
            if candidate.page_count != original.page_count:
                raise VerificationError("Seitenzahl wurde verändert.")
            if candidate.metadata != orig_metadata:
                raise VerificationError("Standard-Metadaten wurden verändert.")
            if candidate.get_xml_metadata() != orig_xmp:
                raise VerificationError("XMP/XML-Metadaten wurden verändert.")
            if candidate.get_toc(simple=True) != orig_toc:
                raise VerificationError("Lesezeichen wurden verändert.")
            if candidate.embfile_count() != orig_embedded:
                raise VerificationError("Eingebettete Dateien wurden verändert.")
            now_ocgs = sorted((v.get("name"), v.get("on"), str(v.get("intent")))
                              for v in candidate.get_ocgs().values())
            if now_ocgs != orig_ocgs:
                raise VerificationError("PDF-Ebenen wurden verändert.")
            if any(_links(candidate[i]) != orig_links[i] for i in range(original.page_count)):
                raise VerificationError("PDF-Links wurden verändert.")
            if any(_annotations(candidate[i]) != orig_annots[i] for i in range(original.page_count)):
                raise VerificationError("PDF-Anmerkungen wurden verändert.")

            for idx in range(original.page_count):
                old, new = original[idx], candidate[idx]
                if old.rect != new.rect or old.rotation != new.rotation:
                    raise VerificationError(f"Seite {idx + 1}: Seitengeometrie wurde verändert.")
                if idx in rects_by_page:
                    rr = rects_by_page[idx]
                    if _text_inside_count(new, rr):
                        raise VerificationError(f"Seite {idx + 1}: Text wurde nicht vollständig entfernt.")
                    if _text_outside(new, rr) != original_outside[idx]:
                        raise VerificationError(f"Seite {idx + 1}: Text außerhalb wurde verändert.")
                    if _drawing_signature(new) != original_vectors[idx]:
                        raise VerificationError(f"Seite {idx + 1}: Vektorgrafiken wurden verändert.")
                    if _image_signature(new) != original_images[idx]:
                        raise VerificationError(f"Seite {idx + 1}: Eingebettete Bilder wurden verändert.")
                for scale in _verification_scales(old, idx in rects_by_page):
                    report(f"Vergleiche Seite {idx + 1}/{original.page_count} bei {scale:.2f}×...")
                    display_rects = [pymupdf.Rect(r) for r in selections.get(idx, ())]
                    _verify_visual_page(old, new, display_rects, scale)

        return ProcessResult(
            pdf_bytes=output, removed_vectors=0, edited_pages=len(rects_by_page),
            metadata_preserved=True,
            verification="Nur Text entfernt; Tabellenlinien/Bilder, Text außerhalb und Metadaten geprüft.",
            method="text_only", removed_text_chars=sum(counts.values()),
            modified_images=0, changes_by_page={idx: 0 for idx in rects_by_page},
        )


def process_pdf_intelligent(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Text-first automatic choice, never inferred from unreliable PDF Z-order."""
    source = Path(input_path)
    with pymupdf.open(source) as original:
        _check_document(original)
        rr = _rectangles(original, selections)
        has_text = []
        has_no_text = []
        for idx, values in selections.items():
            if idx not in rr:
                continue
            page = original[idx]
            for display in values:
                rect = _page_coords(page, _as_rect(display))
                # Prefer center-based character selection in automatic mode.
                # CAD title blocks often have a neighboring page-grid label whose
                # glyph bbox barely touches a logo selection (without visual ink).
                # A mere bbox overlap must not trigger destructive text removal.
                if any(rect.contains(pymupdf.Point((bb.x0 + bb.x1)/2, (bb.y0 + bb.y1)/2))
                       for bb, _sig in _text_chars(page)):
                    has_text.append((idx, rect))
                else:
                    has_no_text.append((idx, rect))
    # Image-object recognition comes first when each marked region mostly
    # covers an embedded image. A nearby table label whose bounding box
    # overlaps the operator's rough rectangle must not divert the workflow
    # to text-only mode. Users can always explicitly select "Nur Text".
    from image_selection import image_candidates
    with pymupdf.open(source) as original:
        all_image_candidates = all(
            bool(image_candidates(original[idx], display))
            for idx, items in selections.items() if idx in rr
            for display in items
        )
    if all_image_candidates:
        from image_only import process_pdf_image_only
        if progress:
            progress("Automatik: Bildlogo erkannt – Bildobjekt wird gezielt entfernt; Tabellenlinien bleiben erhalten.")
        return process_pdf_image_only(source, selections, progress=progress)

    if has_text and has_no_text:
        raise EditError(
            "Automatikmodus: Einige Rechtecke enthalten Text, andere nur Grafiken/Bilder. "
            "Bitte die Bereiche in zwei Durchgängen bearbeiten oder explizit Universalmodus wählen."
        )
    if has_text:
        if progress:
            progress("Automatik: Text erkannt — entferne ausschließlich Text; Tabellen bleiben erhalten.")
        result = process_pdf_text_only(source, selections, progress=progress)
        result.method = "intelligent_text"
        return result
    # Prefer isolated raster-logo removal if every selected area contains at
    # least one fully enclosed embedded image, even where a table vector path
    # crosses the selected rectangle. The image-only engine preserves that path.
    with pymupdf.open(source) as original:
        image_only_candidate = True
        for idx, rect_list in rr.items():
            page = original[idx]
            for rect in rect_list:
                overlap = [im for im in page.get_image_info(xrefs=True)
                           if rect.intersects(pymupdf.Rect(im["bbox"]))]
                if not overlap or not all(rect.contains(pymupdf.Rect(im["bbox"])) for im in overlap):
                    image_only_candidate = False
                    break
            if not image_only_candidate:
                break
    if image_only_candidate:
        from image_only import process_pdf_image_only
        if progress:
            progress("Automatik: eingebettetes Bild erkannt — lösche nur Bilder; Tabellenlinien bleiben erhalten.")
        return process_pdf_image_only(source, selections, progress=progress)
    if progress:
        progress("Automatik: kein PDF-Text / vollständig erfasstes Bild erkannt — verwende Universalmodus.")
    return process_pdf_universal(source, selections, progress=progress)
