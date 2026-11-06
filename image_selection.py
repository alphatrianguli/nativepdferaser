"""Image-object selection and safe snapping from approximate mouse rectangles."""
from __future__ import annotations
from collections import Counter
from typing import Mapping, Sequence
import pymupdf
from engine import _as_rect, _page_coords, EditError


def _shared_area(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    q = a & b
    return max(0.0, q.width) * max(0.0, q.height) if not q.is_empty else 0.0


def image_candidates(page: pymupdf.Page, display_rect: pymupdf.Rect, *, min_coverage: float = 0.55) -> list[dict]:
    """Images whose visual placement is mostly covered by the user selection.

    A slight miss along the logo edge no longer causes accidental deletion of
    table vectors. Small incidental overlaps with an adjacent image are ignored.
    The threshold is deliberately conservative: thumbnails only grazed by the
    rectangle should never become deletion targets.
    """
    rect = _page_coords(page, _as_rect(display_rect))
    chosen = []
    for im in page.get_image_info(xrefs=True):
        bbox = pymupdf.Rect(im['bbox'])
        if bbox.is_empty or not rect.intersects(bbox):
            continue
        coverage = _shared_area(rect, bbox) / (bbox.width * bbox.height)
        center = pymupdf.Point((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2)
        # Center alone is not enough: a very narrow stripe through the center
        # cannot be interpreted as an intended whole-image selection.
        if coverage >= min_coverage:
            chosen.append(im)
    return chosen


def bbox_to_display(page: pymupdf.Page, im: dict) -> pymupdf.Rect:
    return pymupdf.Rect(pymupdf.Rect(im['bbox']) * page.rotation_matrix)


def snap_image_selections(doc: pymupdf.Document, selections: Mapping[int, Sequence]) -> tuple[dict[int, list[pymupdf.Rect]], dict[int, list[dict]]]:
    """Return exact image bounding boxes (display coordinates) and image details.

    No source file or original selections are modified. A selection must cover
    at least 55% of any image it wants to remove. Partial snippets are rejected.
    """
    if not selections or not any(selections.values()):
        raise EditError('Bitte ein oder mehrere Bildlogos markieren.')
    snapped: dict[int, list[pymupdf.Rect]] = {}
    images: dict[int, list[dict]] = {}
    for idx, values in selections.items():
        if not isinstance(idx, int) or idx < 0 or idx >= doc.page_count:
            raise EditError('Ungültige Seitennummer.')
        page = doc[idx]
        page_images = []
        page_rects = []
        existing = set()
        for val in values:
            display_rect = _as_rect(val)
            if not page.rect.contains(display_rect):
                raise EditError(f'Seite {idx+1}: Rechteck liegt außerhalb der Seite.')
            hit = image_candidates(page, display_rect)
            if not hit:
                raise EditError(
                    f'Seite {idx+1}: Das Bildlogo ist nicht vollständig bzw. nicht ausreichend markiert '
                    '(mindestens ca. 55 % der Bildfläche). Bitte das Bild genauer markieren '
                    'oder „Bildlogo exakt erfassen“ wählen.'
                )
            for im in hit:
                sig = (im['xref'], tuple(round(v,3) for v in im['bbox']), im.get('number'))
                if sig in existing:
                    continue
                existing.add(sig)
                page_images.append(im)
                page_rects.append(bbox_to_display(page, im))
        if page_images:
            snapped[idx] = page_rects
            images[idx] = page_images
    if not images:
        raise EditError('Keine eingebetteten Bildlogos erkannt.')
    return snapped, images
