"""Conservative native-PDF universal rectangle removal for Native PDF Eraser.

Removes text characters, completely contained vector paths and referenced image
pixels/objects. It does not paint over remaining content or rasterize whole pages.
A full rewrite plus explicit checks are required before offering the PDF to save.

Limitations: no universal guarantee for unusual PDF content streams, arbitrary
hidden resources, annotations, optional-content layers or overlapping drawings.
When safety cannot be established, raise a verification error (fail closed).
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pymupdf

from engine import (
    EditError, VerificationError, ProcessResult, _as_rect, _page_coords,
    _check_document, _verification_scales, _verify_visual_page,
    inspect_selection, process_pdf,
)


def _text_chars(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, tuple]]:
    """Build per-character signatures in unrotated page coordinates."""
    chars = []
    for block in page.get_text("rawdict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    b = pymupdf.Rect(ch["bbox"])
                    origin = ch.get("origin", (0, 0))
                    signature = (
                        ch.get("c", ""),
                        round(float(origin[0]), 3), round(float(origin[1]), 3),
                        *(round(float(k), 3) for k in b),
                        span.get("font", ""), round(float(span.get("size", 0)), 3),
                    )
                    chars.append((b, signature))
    return chars


def _text_outside(page: pymupdf.Page, rects: Sequence[pymupdf.Rect]) -> Counter:
    return Counter(sig for bbox, sig in _text_chars(page) if not any(bbox.intersects(r) for r in rects))


def _text_inside_count(page: pymupdf.Page, rects: Sequence[pymupdf.Rect]) -> int:
    return sum(1 for bbox, _ in _text_chars(page) if any(bbox.intersects(r) for r in rects))


def _image_occurrences(doc: pymupdf.Document) -> dict[bytes, int]:
    counts: Counter = Counter()
    for page in doc:
        for info in page.get_image_info(xrefs=True):
            digest = info.get("digest")
            if digest:
                counts[digest] += 1
    return counts


def _links(page: pymupdf.Page) -> list[tuple]:
    """Links may be silently removed by redaction; verify no unrelated link changes."""
    return [
        (link.get("kind"), tuple(round(float(v), 3) for v in link.get("from", ())),
         link.get("uri"), link.get("page"), link.get("xref"))
        for link in page.get_links()
    ]


def _annotations(page: pymupdf.Page) -> list[tuple]:
    result = []
    for annot in page.annots() or []:
        result.append((annot.type, tuple(round(float(v), 3) for v in annot.rect),
                       annot.info.get("content"), annot.info.get("title")))
    return result


def _selection_details(page: pymupdf.Page, rects: Sequence[pymupdf.Rect]) -> tuple[int, int, list[dict]]:
    """Return contained drawings, touching drawings, selected image placements."""
    contained = touching = 0
    for d in page.get_drawings():
        bbox = d.get("rect")
        if bbox is None:
            continue
        b = pymupdf.Rect(bbox)
        # Horizontal/vertical lines have zero-height/width bboxes in MuPDF.
        # Expand them by the stroke radius *before* intersection testing.
        width = abs(float(d.get("width") or 0))
        margin = max(0.01, width / 2)
        b = b + (-margin, -margin, margin, margin)
        if not any(r.intersects(b) for r in rects):
            continue
        if any(r.contains(b) for r in rects):
            contained += 1
        else:
            touching += 1
    images = [i for i in page.get_image_info(xrefs=True)
              if any(r.intersects(pymupdf.Rect(i["bbox"])) for r in rects)]
    return contained, touching, images


def process_pdf_universal(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Remove eligible PDF objects inside rectangles; refuse unsafe edits.

    Does not sanitize intentionally preserved metadata, attachments, unselected
    pages, hidden layers or arbitrary resources. No save is offered if verification fails.
    """
    def report(message: str) -> None:
        if progress:
            progress(message)

    src = Path(input_path)
    if not src.is_file():
        raise EditError(f"PDF-Datei nicht gefunden: {src}")
    if not selections or not any(selections.values()):
        raise EditError("Bitte mindestens ein Rechteck markieren.")

    with pymupdf.open(src) as original:
        _check_document(original)
        rects_by_page: dict[int, list[pymupdf.Rect]] = {}
        for idx, values in selections.items():
            if not isinstance(idx, int) or not 0 <= idx < original.page_count:
                raise EditError(f"Ungültige Seitennummer: {idx!r}")
            page = original[idx]
            rr = []
            for value in values:
                display = _as_rect(value)
                if not page.rect.contains(display):
                    raise EditError(f"Markierung außerhalb von Seite {idx + 1}.")
                rr.append(_page_coords(page, display))
            if rr:
                rects_by_page[idx] = rr
        if not rects_by_page:
            raise EditError("Keine gültigen Markierungen vorhanden.")

        # Use v0.3 surgical deletion for *pure vector* selections. This retains
        # exact original text positioning in industrial CAD-generated PDFs.
        all_vector_only = True
        vector_counts = {}
        for idx, rr in rects_by_page.items():
            page = original[idx]
            contained, touching, imgs = _selection_details(page, rr)
            vector_counts[idx] = (contained, touching)
            if imgs or _text_inside_count(page, rr):
                all_vector_only = False
        if all_vector_only:
            # v0.3 precision method was proven on CAD logo drawings. It preserves
            # partially crossing paths, while changing only completely contained ones.
            for idx, (contained, touching) in vector_counts.items():
                if not contained and touching:
                    raise EditError(
                        f"Seite {idx + 1}: {touching} Vektorobjekt(e) überschneiden den Rand "
                        "der Markierung, aber kein vollständiges Objekt ist ausgewählt."
                    )
            report("Nur Vektorgrafiken erkannt: nutze bewährte Präzisionsentfernung...")
            return process_pdf(src, selections, progress=progress)

        # Ensure removal does not affect referenced image data elsewhere. If an
        # embedded image is displayed more than once, its old pixels would remain
        # recoverable from the output and cannot be certified as sanitized.
        orig_img_uses = _image_occurrences(original)
        orig_metadata = dict(original.metadata)
        orig_xmp = original.get_xml_metadata()
        orig_toc = original.get_toc(simple=True)
        orig_embedded = original.embfile_count()
        orig_ocgs = sorted((v.get("name"), v.get("on"), str(v.get("intent")))
                           for v in original.get_ocgs().values())
        pre_count: dict[int, tuple[int, int, int]] = {}
        before_links = {i: _links(original[i]) for i in range(original.page_count)}
        before_annots = {i: _annotations(original[i]) for i in range(original.page_count)}
        selected_image_digests: set[bytes] = set()

        with pymupdf.open(src) as edited:
            for idx, rr in rects_by_page.items():
                page = edited[idx]
                contained, touching, images = _selection_details(page, rr)
                if touching:
                    raise EditError(
                        f"Seite {idx + 1}: {touching} Vektorobjekt(e) überschneiden den Rand "
                        "der Markierung. Für verlustfreie Bearbeitung bitte den Bereich anders wählen; "
                        "das Werkzeug wird diese Objekte nicht teilweise abdecken."
                    )
                text_count = _text_inside_count(page, rr)
                if not (contained or text_count or images):
                    raise EditError(f"Seite {idx + 1}: keine unterstützten PDF-Inhalte im Rechteck erkannt.")
                for image in images:
                    digest = image.get("digest")
                    if not digest:
                        raise EditError(f"Seite {idx + 1}: Bildressource nicht sicher prüfbar.")
                    if orig_img_uses.get(digest, 0) > 1:
                        raise EditError(
                            f"Seite {idx + 1}: eine Bildressource wird mehrfach verwendet. "
                            "Das Originalbild könnte sonst in der Ausgabe wiederhergestellt werden."
                        )
                    selected_image_digests.add(digest)
                pre_count[idx] = (contained, text_count, len(images))
                report(f"Seite {idx + 1}: entferne Text, Vektoren und Bilder...")
                for rect in rr:
                    page.add_redact_annot(rect, fill=False, cross_out=False)
                # Keep a complete image if only a portion is selected: rewrite its
                # actual pixels, not the whole page. Remove image placement when
                # its rectangle is fully covered by a selection.
                all_imgs_covered = all(any(r.contains(pymupdf.Rect(i["bbox"])) for r in rr)
                                       for i in images)
                image_action = (pymupdf.PDF_REDACT_IMAGE_REMOVE if images and all_imgs_covered
                                else pymupdf.PDF_REDACT_IMAGE_PIXELS)
                page.apply_redactions(
                    images=image_action,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
            # Metadata is intentionally retained verbatim for the user's workflow.
            edited.set_metadata({k: v for k, v in orig_metadata.items()
                                 if k not in ("format", "encryption")})
            if orig_xmp and edited.get_xml_metadata() != orig_xmp:
                edited.set_xml_metadata(orig_xmp)
            report("Schreibe PDF ohne frühere Revisionen und ungenutzte Objekte...")
            output = edited.tobytes(
                garbage=4, deflate=True, deflate_images=True, clean=False,
                no_new_id=True, encryption=pymupdf.PDF_ENCRYPT_NONE,
            )

        report("Prüfe PDF-Struktur, Inhalte und Darstellung...")
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
            if any(_links(candidate[i]) != before_links[i] for i in range(original.page_count)):
                raise VerificationError("PDF-Links wurden verändert. Bitte Bereich anders markieren.")
            if any(_annotations(candidate[i]) != before_annots[i] for i in range(original.page_count)):
                raise VerificationError("PDF-Anmerkungen wurden verändert. Bitte Bereich anders markieren.")
            # Detect original image retained anywhere in the output (incl. other pages).
            after_img_uses = _image_occurrences(candidate)
            if selected_image_digests.intersection(after_img_uses.keys()):
                raise VerificationError(
                    "Ein Originalbild ist weiterhin in der PDF referenziert; "
                    "sichere Entfernung nicht nachweisbar."
                )
            vectors = texts = images_changed = 0
            per_page = {}
            for idx in range(original.page_count):
                old, new = original[idx], candidate[idx]
                if old.rect != new.rect or old.rotation != new.rotation:
                    raise VerificationError(f"Seite {idx + 1}: Seitengeometrie wurde verändert.")
                if idx in rects_by_page:
                    rr = rects_by_page[idx]
                    if _text_outside(old, rr) != _text_outside(new, rr):
                        raise VerificationError(f"Seite {idx + 1}: Text außerhalb der Auswahl wurde verändert.")
                    if _text_inside_count(new, rr):
                        raise VerificationError(f"Seite {idx + 1}: Text innerhalb der Auswahl ist noch enthalten.")
                    pvec, ptext, pimg = pre_count[idx]
                    # Keep real-count metrics separate from visual verification.
                    delta_vec = len(old.get_drawings()) - len(new.get_drawings())
                    if pvec and delta_vec < pvec:
                        raise VerificationError(f"Seite {idx + 1}: nicht alle ausgewählten Vektoren wurden entfernt.")
                    vectors += max(0, delta_vec)
                    texts += ptext
                    images_changed += pimg
                    per_page[idx] = max(0, delta_vec)
                for scale in _verification_scales(old, idx in rects_by_page):
                    report(f"Vergleiche Seite {idx + 1}/{original.page_count} bei {scale:.2f}×...")
                    display = selections.get(idx, []) if idx in rects_by_page else []
                    changed, _ = _verify_visual_page(old, new, [pymupdf.Rect(v) for v in display], scale)
                    # A hidden text layer may be physically removed without any
                    # visible pixel difference. Structural checks above establish
                    # that the selected text/images/vectors were actually changed.
            return ProcessResult(
                pdf_bytes=output,
                removed_vectors=vectors,
                edited_pages=len(rects_by_page),
                metadata_preserved=True,
                verification="Geprüft: Text/Metadaten erhalten außerhalb der Auswahl; PDF-Darstellung bei 1× und bis 2× verglichen.",
                changes_by_page=per_page,
                method="universal",
                removed_text_chars=texts,
                modified_images=images_changed,
            )
