"""Native PDF Eraser intelligent mixed-mode removal.

Classifies each selection independently, then composes the already verified
image-only, text-only and vector-only engines in separate passes. All edits
operate on a temporary copy; the original file remains untouched. This avoids
passing crossing title-block vectors to universal redaction when the user
selected an image and a text field in the same document.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Mapping, Sequence

import pymupdf

from engine import (EditError, VerificationError, ProcessResult, _as_rect, _page_coords,
                    _check_document, _verification_scales, _verify_visual_page,
                    process_pdf)
from image_selection import image_candidates, bbox_to_display
from image_only import process_pdf_image_only
from text_only import process_pdf_text_only
from universal import _text_chars, _text_outside, process_pdf_universal


def _add(target: dict[int, list[pymupdf.Rect]], idx: int, value):
    target.setdefault(idx, []).append(pymupdf.Rect(value))


def _character_centers(page: pymupdf.Page, rect: pymupdf.Rect) -> bool:
    return any(rect.contains(pymupdf.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2))
               for bb, _ in _text_chars(page))


def classify_selections(doc: pymupdf.Document, selections: Mapping) -> tuple[dict, dict, dict]:
    """Return (image, text, graphic) selections, allowing text+image in one box.

    Image detection requires substantial coverage of *the image*, not merely a
    small overlap. Minor overlap with a vector table border is ignored by the
    image/text workflows. For a partial scanned-page image fall back to the
    conservative universal engine, which may reject unsupported cases.
    """
    if not selections or not any(selections.values()):
        raise EditError('Bitte mindestens einen Bereich auswählen.')
    image_rects: dict[int, list[pymupdf.Rect]] = {}
    text_rects: dict[int, list[pymupdf.Rect]] = {}
    graphic_rects: dict[int, list[pymupdf.Rect]] = {}
    for idx, values in selections.items():
        if not isinstance(idx, int) or not 0 <= idx < doc.page_count:
            raise EditError(f'Ungültige Seitennummer: {idx!r}')
        page = doc[idx]
        for value in values:
            r = _as_rect(value)
            if not page.rect.contains(r):
                raise EditError(f'Seite {idx+1}: Markierung außerhalb der Seite.')
            unrotated = _page_coords(page, r)
            images = image_candidates(page, r)
            text = _character_centers(page, unrotated)
            if images:
                _add(image_rects, idx, r)
            if text and not images:
                _add(text_rects, idx, r)
            elif text and images:
                # A rough image selection may graze nearby native table text.
                # Only treat it as a combined text+image selection when native
                # glyphs actually lie within the detected image's true bbox.
                # Otherwise the operator must mark the text separately.
                image_boxes = [pymupdf.Rect(im['bbox']) for im in images]
                # A genuinely wide selection can intentionally contain both a
                # logo and separate table text. Ignore only *edge grazes* of
                # neighboring text, not clearly enclosed text in its own cell.
                from universal import _text_chars
                for bb, _sig in _text_chars(page):
                    pt = pymupdf.Point((bb.x0+bb.x1)/2, (bb.y0+bb.y1)/2)
                    if not unrotated.contains(pt):
                        continue
                    inside_image = any(box.contains(pt) for box in image_boxes)
                    safely_inside = min(pt.x-unrotated.x0, unrotated.x1-pt.x,
                                        pt.y-unrotated.y0, unrotated.y1-pt.y) >= 6.0
                    if inside_image or safely_inside:
                        _add(text_rects, idx, r)
                        break
            if not images and not text:
                _add(graphic_rects, idx, r)
    return image_rects, text_rects, graphic_rects


def process_pdf_smart_mixed(
    input_path: str | Path,
    selections: Mapping[int, Sequence[Sequence[float] | pymupdf.Rect]],
    progress: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Delete selected text and embedded images in one operation; retain tables.

    The verified legacy engines are applied sequentially. A final full-document
    render/metadata check compares the combined output to the original, using
    only the actual approved removal bounds. Unsupported edits fail closed.
    """
    source = Path(input_path)
    if not source.is_file():
        raise EditError(f'PDF-Datei nicht gefunden: {source}')
    def report(text):
        if progress:
            progress(text)

    with pymupdf.open(source) as original:
        _check_document(original)
        image_rects, text_rects, graphic_rects = classify_selections(original, selections)
        # On the image stage, bounds may be expanded to the full image object.
        # The GUI asks permission when expansion is necessary.
        allowed = {i:[pymupdf.Rect(v) for v in values] for i, values in selections.items() if values}
        for idx, values in image_rects.items():
            page = original[idx]
            for rect in values:
                for im in image_candidates(page, rect):
                    allowed[idx].append(bbox_to_display(page, im))
        before_md = dict(original.metadata)
        before_xmp = original.get_xml_metadata()
        # Differentiate vector-only selections from *partial* image selections
        # (such as an area of a scanned page) so universal pixel editing is not
        # accidentally lost in v0.8. The universal path is conservative and may
        # still reject content crossing selection boundaries.
        vector_rects: dict[int, list[pymupdf.Rect]] = {}
        partial_images: dict[int, list[pymupdf.Rect]] = {}
        for idx, values in graphic_rects.items():
            page = original[idx]
            for value in values:
                unrotated = _page_coords(page, value)
                has_partial = any(unrotated.intersects(pymupdf.Rect(im['bbox']))
                                  for im in page.get_image_info(xrefs=True))
                _add(partial_images if has_partial else vector_rects, idx, value)
        stages = []
        if image_rects:
            stages.append(('Bilder', image_rects, process_pdf_image_only))
        if text_rects:
            stages.append(('Text', text_rects, process_pdf_text_only))
        if vector_rects:
            # Use the proven vector-only engine for CAD/vector logos.
            stages.append(('Vektorgrafiken', vector_rects, process_pdf))
        if partial_images:
            stages.append(('Bildbereiche', partial_images, process_pdf_universal))
        if not stages:
            raise EditError('Keine unterstützten PDF-Inhalte erkannt.')

        with TemporaryDirectory(prefix='native_pdf_eraser_') as tmp:
            stage_input = source
            results: list[ProcessResult] = []
            for i, (label, subset, fn) in enumerate(stages):
                report(f'{i+1}/{len(stages)}: {label} entfernen und prüfen ...')
                # Every stage verifies the previously edited document without
                # modifying the input PDF. Successive stages inherit prior edits.
                result = fn(stage_input, subset, progress=progress)
                results.append(result)
                next_path = Path(tmp) / f'schritt_{i+1}.pdf'
                next_path.write_bytes(result.pdf_bytes)
                stage_input = next_path
            output = results[-1].pdf_bytes

        with pymupdf.open(stream=output, filetype='pdf') as final:
            if final.page_count != original.page_count:
                raise VerificationError('Die Seitenzahl wurde verändert.')
            if final.metadata != before_md or final.get_xml_metadata() != before_xmp:
                raise VerificationError('Metadaten wurden beim Kombinieren verändert.')
            for idx in range(original.page_count):
                before, after = original[idx], final[idx]
                if before.rect != after.rect or before.rotation != after.rotation:
                    raise VerificationError(f'Seite {idx+1}: Seitengröße/Rotation verändert.')
                # Text outside text selections must retain its exact glyph geometry.
                if _text_outside(before, [_page_coords(before, r) for r in text_rects.get(idx, [])]) != \
                   _text_outside(after, [_page_coords(after, r) for r in text_rects.get(idx, [])]):
                    raise VerificationError(f'Seite {idx+1}: Text außerhalb der Auswahl verändert.')
                for scale in _verification_scales(before, idx in allowed):
                    report(f'Endprüfung: Seite {idx+1}/{original.page_count} bei {scale:.2f}× ...')
                    _verify_visual_page(before, after, allowed.get(idx, []), scale)

        methods = {name for name, _subset, _fn in stages}
        return ProcessResult(
            pdf_bytes=output,
            removed_vectors=sum(r.removed_vectors for r in results),
            edited_pages=len(allowed),
            metadata_preserved=True,
            verification='Kombinierte Inhaltsentfernung und Vergleich mit Original erfolgreich.',
            method=('smart_mixed' if len(methods) > 1 else ('intelligent_text' if methods == {'Text'} else results[0].method)),
            removed_text_chars=sum(r.removed_text_chars for r in results),
            modified_images=sum(r.modified_images for r in results),
            changes_by_page={i:sum(r.changes_by_page.get(i,0) for r in results) for i in allowed},
        )
