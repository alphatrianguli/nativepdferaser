"""Conservative, inspectable object-boundary detection for a drawn PDF rectangle.

Recognizes only whole embedded images (majority coverage) or compact vector
paths (majority coverage). Never interprets a page-spanning table/grid border
as a candidate object. Recognition modifies a *selection*, not PDF content.
The actual editing engine still performs its independent preservation checks.
"""
from __future__ import annotations
from dataclasses import dataclass
import pymupdf
from engine import _page_coords
from image_selection import bbox_to_display, image_candidates


@dataclass(frozen=True)
class RecognizedSelection:
    rect: pymupdf.Rect
    kind: str
    objects: int = 0


def _area(rect: pymupdf.Rect) -> float:
    return max(0.0, rect.width) * max(0.0, rect.height)


def detect_object(page: pymupdf.Page, display_rect: pymupdf.Rect, mode: str = 'intelligent') -> RecognizedSelection:
    """Suggest exact image/vector bounding boxes; leave ambiguous rectangles alone.

    Coordinates are always **display** points, even for rotated pages.
    Text takes priority in intelligent mode when no image is identified.
    A selected image and accompanying text retain their union as the target.
    """
    requested = pymupdf.Rect(display_rect)
    if mode == 'text_only':
        return RecognizedSelection(requested, 'text')
    local = _page_coords(page, requested)
    images = image_candidates(page, requested, min_coverage=0.50) if mode in ('intelligent', 'image_only', 'universal') else []
    # A moderately rough rectangle is enough only when the user also marked
    # the image's centre. This prevents deleting a nearby, incidentally grazed
    # image without an explicit central selection.
    images = [im for im in images if local.contains(pymupdf.Point(
        (im['bbox'][0]+im['bbox'][2])/2, (im['bbox'][1]+im['bbox'][3])/2))]
    if images:
        bounds = bbox_to_display(page, images[0])
        for img in images[1:]:
            bounds |= bbox_to_display(page, img)
        if mode in ('intelligent', 'universal'):
            # Retain explicit user-selected text when an image is also present.
            from smart_mixed import _character_centers
            if _character_centers(page, local):
                bounds |= requested
                return RecognizedSelection(bounds, 'image+text', len(images))
        return RecognizedSelection(bounds, 'image', len(images))
    if mode == 'image_only':
        return RecognizedSelection(requested, 'manual')

    # Native PDF text in a table is *not* a vector logo. Do not expand its box.
    if mode in ('intelligent', 'universal'):
        from smart_mixed import _character_centers
        if _character_centers(page, local):
            return RecognizedSelection(requested, 'text')

    if mode not in ('intelligent', 'universal', 'precision'):
        return RecognizedSelection(requested, 'manual')

    # Take paths that are largely covered, compact relative to the user box.
    # Excluding long border paths is crucial for title blocks and tables.
    compact = []
    for drawing in page.get_drawings():
        if drawing.get('rect') is None:
            continue
        box = pymupdf.Rect(drawing['rect'])
        if box.is_empty or box.width <= 0 or box.height <= 0:
            # Diagonal / horizontal stroke shapes may have a zero-height bbox;
            # use the unmodified selection instead of guessing.
            continue
        if box.width > local.width * 1.35 or box.height > local.height * 1.35:
            continue
        overlap = _area(box & local)
        if overlap / max(_area(box), 1e-6) >= 0.76:
            compact.append(box)

    if not compact:
        return RecognizedSelection(requested, 'manual')

    bounds = pymupdf.Rect(compact[0])
    for item in compact[1:]:
        bounds |= item
    # A small tolerance encloses anti-aliasing/stroke thickness; it is also
    # clamped to the page boundaries. A large expansion indicates ambiguity.
    margin = 0.6
    bounds = pymupdf.Rect(bounds.x0-margin, bounds.y0-margin, bounds.x1+margin, bounds.y1+margin)
    if bounds.width > local.width * 1.25 or bounds.height > local.height * 1.25:
        return RecognizedSelection(requested, 'manual')
    page_bounds = page.rect * page.derotation_matrix
    bounds &= page_bounds
    displayed = pymupdf.Rect(bounds * page.rotation_matrix)
    return RecognizedSelection(displayed, 'vector', len(compact))
