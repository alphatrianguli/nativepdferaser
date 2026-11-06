"""Image-only removal with all-occurrence validation for shared PDF image resources.

Only remove whole, fully enclosed image placements. Preserve text and vectors.
When an image is shared across pages, ALL occurrences must be selected to avoid
leaving the confidential image on another page. Full rewrite + validation.
"""
from __future__ import annotations

from collections import Counter
from image_selection import snap_image_selections
from image_surgical import try_remove_isolated_images
from pathlib import Path
from typing import Callable, Mapping, Sequence
import pymupdf

from engine import EditError, VerificationError, ProcessResult, _check_document, _verification_scales, _verify_visual_page
from text_only import _rectangles, _drawing_signature, _image_signature
from universal import _text_chars, _links, _annotations


def _images_for_rectangle(page: pymupdf.Page, rects: Sequence[pymupdf.Rect]):
    return [im for im in page.get_image_info(xrefs=True)
            if any(r.intersects(pymupdf.Rect(im["bbox"])) for r in rects)]


def process_pdf_image_only(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Delete fully covered raster logo placements; fail closed on unsafe reuse."""
    def report(message):
        if progress:
            progress(message)
    source = Path(input_path)
    if not source.is_file():
        raise EditError(f"PDF-Datei nicht gefunden: {source}")
    with pymupdf.open(source) as original:
        _check_document(original)
        # Employees select approximately. Snap to the actual embedded image
        # bounding boxes, so crossing title-block lines are not target objects.
        snapped_display, chosen_images = snap_image_selections(original, selections)
        rects = _rectangles(original, snapped_display)  # unrotated PDF coordinates
        all_uses = Counter()
        selected_uses = Counter()
        original_unselected_images = {}
        original_text = {}
        original_vectors = {}
        orig_meta = dict(original.metadata)
        orig_xmp = original.get_xml_metadata()
        orig_toc = original.get_toc(simple=True)
        orig_embedded = original.embfile_count()
        orig_ocgs = sorted((v.get("name"), v.get("on"), str(v.get("intent"))) for v in original.get_ocgs().values())
        orig_links = {i:_links(p) for i,p in enumerate(original)}
        orig_annots = {i:_annotations(p) for i,p in enumerate(original)}
        for idx, p in enumerate(original):
            for im in p.get_image_info(xrefs=True):
                if im.get("digest"):
                    all_uses[im["digest"]] += 1
        for idx, rr in rects.items():
            page = original[idx]
            touching = chosen_images[idx]
            if not touching:
                raise EditError(f"Seite {idx+1}: Kein eingebettetes Bild im markierten Bereich.")
            for im in touching:
                b = pymupdf.Rect(im["bbox"])
                if not any(r.contains(b) for r in rr):
                    raise EditError(f"Seite {idx+1}: Das Bild ist nicht vollständig markiert. Bitte Rechteck vergrößern.")
                if not im.get("digest"):
                    raise EditError(f"Seite {idx+1}: Bildressource kann nicht überprüft werden.")
                selected_uses[im["digest"]] += 1
            orig_sigs = _image_signature(page)
            for im in touching:
                sig=(im.get("digest"),tuple(round(float(v),4) for v in im.get("bbox",())),im.get("width"),im.get("height"))
                orig_sigs[sig] -= 1
                if not orig_sigs[sig]: del orig_sigs[sig]
            original_unselected_images[idx] = orig_sigs
            original_text[idx] = _text_chars(page)
            original_vectors[idx] = _drawing_signature(page)
        for digest, n in selected_uses.items():
            if n != all_uses[digest]:
                raise EditError(
                    f"Dieses Bild kommt auf {all_uses[digest]} Seite(n)/Positionen vor, "
                    f"aber nur {n} Vorkommen sind markiert. "
                    "Bitte zuerst 'Gleiche Logos auf anderen Seiten finden' verwenden "
                    "oder alle Vorkommen selbst markieren."
                )
        with pymupdf.open(source) as edited:
            # First try direct, whole-object image deletion without PDF redaction.
            # This is more precise on CAD drawing title blocks than applying
            # redactions, which can rebuild/redraw unrelated contents.
            surgical = try_remove_isolated_images(edited, chosen_images)
            if surgical:
                report('Bild-Zeichenbefehle direkt entfernt; Tabellen und Text unverändert.')
            else:
                report('Komplexe Bildstruktur: native Bildentfernung mit strenger Prüfung...')
                for idx, rr in rects.items():
                    page = edited[idx]
                    for r in rr:
                        page.add_redact_annot(r,fill=False,cross_out=False)
                    page.apply_redactions(
                        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                        text=pymupdf.PDF_REDACT_TEXT_NONE,
                    )
            edited.set_metadata({k:v for k,v in orig_meta.items() if k not in ("format","encryption")})
            if orig_xmp and edited.get_xml_metadata() != orig_xmp:
                edited.set_xml_metadata(orig_xmp)
            output = edited.tobytes(
                garbage=4,deflate=True,deflate_images=True,clean=False,
                no_new_id=True,encryption=pymupdf.PDF_ENCRYPT_NONE,
            )
        with pymupdf.open(stream=output,filetype='pdf') as verified:
            if verified.page_count != original.page_count:
                raise VerificationError("Seitenzahl wurde verändert.")
            if verified.metadata != orig_meta or verified.get_xml_metadata() != orig_xmp:
                raise VerificationError("Metadaten wurden verändert.")
            if verified.get_toc(simple=True) != orig_toc or verified.embfile_count() != orig_embedded:
                raise VerificationError("Lesezeichen oder eingebettete Dateien wurden verändert.")
            current_ocgs = sorted((v.get("name"),v.get("on"),str(v.get("intent"))) for v in verified.get_ocgs().values())
            if current_ocgs != orig_ocgs:
                raise VerificationError("Ebenen wurden verändert.")
            all_after_digests = set()
            for idx, page in enumerate(verified):
                before = original[idx]
                if before.rect != page.rect or before.rotation != page.rotation:
                    raise VerificationError(f"Seite {idx+1}: Seitengeometrie wurde verändert.")
                if _links(page) != orig_links[idx] or _annotations(page) != orig_annots[idx]:
                    raise VerificationError(f"Seite {idx+1}: Links oder Annotationen wurden verändert.")
                all_after_digests.update(im.get('digest') for im in page.get_image_info(xrefs=True))
                if idx in rects:
                    if _text_chars(page) != original_text[idx]:
                        raise VerificationError(f"Seite {idx+1}: Text oder Zeichenpositionen wurden verändert.")
                    if _drawing_signature(page) != original_vectors[idx]:
                        raise VerificationError(f"Seite {idx+1}: Vektorgrafiken/Tabelle wurden verändert.")
                    if _image_signature(page) != original_unselected_images[idx]:
                        raise VerificationError(f"Seite {idx+1}: Bilder außerhalb der Auswahl wurden verändert.")
                for scale in _verification_scales(before, idx in rects):
                    report(f"Vergleiche Seite {idx+1}/{original.page_count} bei {scale:.2f}×...")
                    _verify_visual_page(before,page,[pymupdf.Rect(r) for r in snapped_display.get(idx,[])],scale)
            if set(selected_uses) & all_after_digests:
                raise VerificationError("Das ursprüngliche Bild ist noch im Dokument referenziert.")
            # garbage=4 writes a new revision without leftover old image streams.
            return ProcessResult(
                pdf_bytes=output, removed_vectors=0, edited_pages=len(rects),
                metadata_preserved=True,
                verification=("Bild-Zeichenbefehle und ungenutzte Bildressourcen direkt entfernt; " if surgical else "Native Bildentfernung; ") + "Text, Tabellen, Metadaten und Ansicht überprüft.",
                method="image_only", removed_text_chars=0,
                modified_images=sum(selected_uses.values()),
                changes_by_page={i:0 for i in rects},
            )
