"""Native PDF Eraser: conservative vector-only PDF removal engine.

Coordinates supplied by the GUI are the displayed (rotated) page coordinates
in PDF points. Original source files are never modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from math import sqrt, isfinite
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pymupdf
from PIL import Image, ImageChops, ImageDraw
from surgical import try_surgical_removal


class EditError(Exception):
    """Input/selection is unsupported or no eligible drawings were found."""


class VerificationError(EditError):
    """The candidate output failed preservation checks. It must not be saved."""


@dataclass(frozen=True)
class SelectionStats:
    eligible_vectors: int = 0
    touching_vectors: int = 0
    overlapping_images: int = 0
    overlapping_text: int = 0


@dataclass
class ProcessResult:
    pdf_bytes: bytes
    removed_vectors: int
    edited_pages: int
    metadata_preserved: bool
    verification: str
    changes_by_page: dict[int, int] = field(default_factory=dict)
    method: str = "native"
    removed_text_chars: int = 0
    modified_images: int = 0


def _as_rect(value: Sequence[float] | pymupdf.Rect) -> pymupdf.Rect:
    try:
        rect = pymupdf.Rect(value)
    except (TypeError, ValueError) as exc:
        raise EditError(f"Ungültiges Rechteck: {value!r}") from exc
    if not all(isfinite(x) for x in rect) or rect.is_empty or rect.width < 2 or rect.height < 2:
        raise EditError("Jede Markierung muss mindestens 2 × 2 PDF-Punkte groß sein.")
    return rect


def _page_coords(page: pymupdf.Page, display_rect: pymupdf.Rect) -> pymupdf.Rect:
    """Convert rendered display coordinates to the page's unrotated PDF coordinates."""
    return pymupdf.Rect(display_rect * page.derotation_matrix)


def _check_document(doc: pymupdf.Document) -> None:
    if not doc.is_pdf:
        raise EditError("Es werden nur PDF-Dateien unterstützt.")
    if doc.needs_pass or doc.is_encrypted:
        raise EditError("Verschlüsselte oder passwortgeschützte PDFs werden in dieser Version nicht unterstützt.")
    if doc.is_form_pdf:
        raise EditError("PDFs mit interaktiven Formularfeldern werden in dieser Version nicht unterstützt.")
    # A signed PDF cannot have its old signature remain cryptographically valid.
    try:
        if doc.get_sigflags() > 0:
            raise EditError("Digital signierte PDFs werden nicht unterstützt. Durch Bearbeitung erlischt die Signatur.")
    except AttributeError:
        pass


def inspect_selection(page: pymupdf.Page, display_rect: Sequence[float] | pymupdf.Rect) -> SelectionStats:
    """Conservative preview estimate; deletion engine still verifies actual output."""
    rect = _page_coords(page, _as_rect(display_rect))
    eligible = touching = 0
    for drawing in page.get_drawings():
        bbox = drawing.get("rect")
        if bbox is None:
            continue
        bbox = pymupdf.Rect(bbox)
        if rect.contains(bbox):
            eligible += 1
        elif rect.intersects(bbox):
            touching += 1
    images = sum(
        bool(rect.intersects(pymupdf.Rect(img["bbox"])))
        for img in page.get_image_info(xrefs=True)
    )
    # Words and numbers are not removed by this vector-only mode.
    text = sum(
        bool(rect.intersects(pymupdf.Rect(word[:4])))
        for word in page.get_text("words")
    )
    return SelectionStats(eligible, touching, images, text)


def _render_pil(page: pymupdf.Page, scale: float) -> Image.Image:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB,
                           alpha=False, annots=True)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _verify_visual_page(
    before: pymupdf.Page,
    after: pymupdf.Page,
    display_rects: Sequence[pymupdf.Rect],
    scale: float,
) -> tuple[int, int]:
    original = _render_pil(before, scale)
    result = _render_pil(after, scale)
    if original.size != result.size:
        raise VerificationError(f"Seite {before.number + 1}: Die Seitengröße wurde verändert.")
    diff = ImageChops.difference(original, result)
    changed_anywhere = int(bool(diff.getbbox()))
    # Erase differences INSIDE the intended areas in the diff image.
    # A small rasterization tolerance accommodates anti-aliasing on the edge.
    if display_rects:
        draw = ImageDraw.Draw(diff)
        for rect in display_rects:
            edge = 3
            coords = (
                int(rect.x0 * scale) - edge, int(rect.y0 * scale) - edge,
                int(rect.x1 * scale + 0.999) + edge,
                int(rect.y1 * scale + 0.999) + edge,
            )
            draw.rectangle(coords, fill=(0, 0, 0))
    if diff.getbbox():
        bbox = diff.getbbox()
        raise VerificationError(
            f"Seite {before.number + 1}: Pixel AUSSERHALB der Markierung wurden verändert "
            f"(Auflösung {scale:.2f}×, ungefährer Bereich {bbox}). Die Ausgabe wurde verworfen."
        )
    return changed_anywhere, 0


def _verification_scales(page: pymupdf.Page, selected: bool) -> list[float]:
    # Bound memory on unusually large drawings; achieve ~two independent resolutions.
    size = page.rect
    pixels = max(1.0, size.width * size.height)
    cap = 11_000_000
    base = min(1.0, sqrt(cap / pixels))
    scales = [base]
    if selected:
        high = min(2.0, sqrt(cap / pixels))
        if high > base * 1.15:
            scales.append(high)
    return scales


def process_pdf(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Remove fully enclosed vector paths; reject if content outside selections changes.

    Returns new PDF bytes only after all checks have passed. The source stays untouched.
    Text, images, and pages without selections are left alone by the redaction operation.
    The full save performs garbage collection and is NOT incremental.
    """
    def report(s: str) -> None:
        if progress:
            progress(s)

    src = Path(input_path)
    if not src.is_file():
        raise EditError(f"PDF-Datei nicht gefunden: {src}")
    if not selections or not any(selections.values()):
        raise EditError("Bitte vor der Verarbeitung mindestens ein Rechteck markieren.")

    original = pymupdf.open(str(src))
    try:
        _check_document(original)
        selection_rects: dict[int, list[pymupdf.Rect]] = {}
        for idx, values in selections.items():
            if not isinstance(idx, int) or not (0 <= idx < original.page_count):
                raise EditError(f"Ungültige Seitennummer: {idx!r}")
            pr = original[idx].rect
            valid: list[pymupdf.Rect] = []
            for value in values:
                rect = _as_rect(value)
                if not pr.contains(rect):
                    raise EditError(f"Eine Markierung liegt außerhalb der Seite {idx + 1}.")
                valid.append(rect)
            if valid:
                selection_rects[idx] = valid
        if not selection_rects:
            raise EditError("Keine gültigen Markierungen vorhanden.")

        # Open a second independent copy: one immutable original, one modified.
        edited = pymupdf.open(str(src))
        try:
            orig_metadata = dict(original.metadata)
            orig_xmp = original.get_xml_metadata()
            orig_toc = original.get_toc(simple=True)
            orig_attachments = original.embfile_count()
            before_text = {i: original[i].get_text("text", sort=False) for i in selection_rects}
            before_paths = {i: len(original[i].get_drawings()) for i in selection_rects}
            # First try exact deletion of isolated CAD path commands.
            # This avoids the native redactor rebuilding text positioning,
            # a problem observed on some industrial CAD-generated PDFs.
            report("Prüfe direktes Entfernen von Vektorbefehlen...")
            surg_rects = {
                idx: [_page_coords(edited[idx], rect) for rect in rects]
                for idx, rects in selection_rects.items()
            }
            surg_counts = try_surgical_removal(edited, surg_rects)
            method = "surgical" if surg_counts is not None else "native"
            if method == "surgical":
                report("Pfadblöcke wurden direkt entfernt; Textbefehle bleiben unverändert.")
            else:
                report("Nutze native Vektorentfernung mit vollständiger Prüfung...")
                for page_idx, display_rects in selection_rects.items():
                    page = edited[page_idx]
                    eligible = sum(
                        1 for dr in page.get_drawings()
                        if any(_page_coords(page, r).contains(pymupdf.Rect(dr["rect"]))
                               for r in display_rects)
                    )
                    if eligible == 0:
                        raise EditError(
                            f"Seite {page_idx + 1}: Keine vollständigen Vektorobjekte im Rechteck. "
                            "Bitte Auswahl vergrößern. Text und Bilder werden nicht entfernt."
                        )
                    for r in display_rects:
                        page.add_redact_annot(_page_coords(page, r), fill=False, cross_out=False)
                    page.apply_redactions(
                        images=pymupdf.PDF_REDACT_IMAGE_NONE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                        text=pymupdf.PDF_REDACT_TEXT_NONE,
                    )
            # Preserve standard metadata even when an editor's save routine would normalize it.
            edited.set_metadata({k: v for k, v in orig_metadata.items() if k not in ("format", "encryption")})
            if orig_xmp and edited.get_xml_metadata() != orig_xmp:
                edited.set_xml_metadata(orig_xmp)
            report("Schreibe vollständige PDF ohne alte Revisionen...")
            output = edited.tobytes(
                garbage=4, deflate=True, clean=False, no_new_id=True,
                encryption=pymupdf.PDF_ENCRYPT_NONE,
            )
        finally:
            edited.close()

        report("Prüfe Metadaten und PDF-Struktur...")
        candidate = pymupdf.open(stream=output, filetype="pdf")
        try:
            if candidate.page_count != original.page_count:
                raise VerificationError("Die Anzahl der Seiten wurde verändert.")
            if candidate.metadata != orig_metadata:
                changed_fields = [k for k in orig_metadata if orig_metadata.get(k) != candidate.metadata.get(k)]
                raise VerificationError("Standard-Metadaten wurden verändert: " + ", ".join(changed_fields))
            if candidate.get_xml_metadata() != orig_xmp:
                raise VerificationError("XMP/XML-Metadaten wurden verändert.")
            if candidate.get_toc(simple=True) != orig_toc:
                raise VerificationError("Lesezeichen / Dokumentgliederung wurden verändert.")
            if candidate.embfile_count() != orig_attachments:
                raise VerificationError("Anzahl eingebetteter Dateien wurde verändert.")
            def _ocg_signature(d):
                return sorted((v.get("name"),v.get("on"),str(v.get("intent")))
                              for v in d.get_ocgs().values())
            if _ocg_signature(candidate) != _ocg_signature(original):
                raise VerificationError("PDF-Ebenen oder deren Sichtbarkeit wurden verändert.")

            removed = 0
            changes_by_page: dict[int, int] = {}
            for idx in range(original.page_count):
                before, after = original[idx], candidate[idx]
                if any(abs(a - b) > 0.001 for a, b in zip(before.rect, after.rect)):
                    raise VerificationError(f"Seite {idx + 1}: Die Seitengeometrie wurde verändert.")
                if before.rotation != after.rotation:
                    raise VerificationError(f"Seite {idx + 1}: Die Seitendrehung wurde verändert.")
                if idx in selection_rects:
                    if after.get_text("text", sort=False) != before_text[idx]:
                        raise VerificationError(f"Seite {idx + 1}: extrahierter Text wurde verändert.")
                    if method == "surgical" and after.get_text("rawdict") != before.get_text("rawdict"):
                        raise VerificationError(f"Seite {idx + 1}: Textzeichen oder Positionen wurden verändert.")
                    delta = before_paths[idx] - len(after.get_drawings())
                    if delta <= 0:
                        raise VerificationError(f"Seite {idx + 1}: Es wurden keine Vektorzeichnungen entfernt.")
                    removed += delta
                    changes_by_page[idx] = delta
                # Check all pages at 1x, modified pages again at up to 2x.
                for scale in _verification_scales(before, idx in selection_rects):
                    report(f"Vergleiche Seite {idx + 1}/{original.page_count} bei {scale:.2f}×...")
                    changed, _ = _verify_visual_page(
                        before, after, selection_rects.get(idx, []), scale
                    )
                    if idx in selection_rects and not changed:
                        raise VerificationError(
                            f"Seite {idx + 1}: Es ist keine sichtbare Änderung bei {scale:.2f}× erkennbar. "
                            "Bitte prüfen, ob das Rechteck das Logo vollständig umfasst."
                        )
            return ProcessResult(
                pdf_bytes=output,
                removed_vectors=removed,
                edited_pages=len(selection_rects),
                metadata_preserved=True,
                verification="Darstellung außerhalb der Markierungen stimmt überein bei 1× und bis zu 2×; Text und Metadaten erhalten.",
                changes_by_page=changes_by_page,
                method=method,
            )
        finally:
            candidate.close()
    finally:
        original.close()
