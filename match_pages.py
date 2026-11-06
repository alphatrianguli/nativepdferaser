"""Conservative same-place repetition discovery, with exact image identity first.

The user initiates detection; matches are proposed, never automatically edited.
For vector/content matching, compare monochrome appearance in the same area.
Only accept high-confidence matches at the same relative page position.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence
from PIL import Image, ImageChops
import pymupdf

from engine import _as_rect, _page_coords
from image_selection import image_candidates, bbox_to_display


@dataclass(frozen=True)
class PageMatch:
    page_index: int
    rect: pymupdf.Rect
    reason: str
    confidence: float


def _rel_rect(r: pymupdf.Rect, source: pymupdf.Rect, target: pymupdf.Rect) -> pymupdf.Rect:
    return pymupdf.Rect(r.x0 / source.width * target.width, r.y0 / source.height * target.height,
                        r.x1 / source.width * target.width, r.y1 / source.height * target.height)


def _crop_signature(page: pymupdf.Page, rect: pymupdf.Rect) -> Image.Image:
    # Render only the candidate region at fixed resolution, using nearest-neighbor
    # resizing and thresholding to avoid minor anti-aliasing differences.
    pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=rect,colorspace=pymupdf.csGRAY,alpha=False)
    im=Image.frombytes('L',(pix.width,pix.height),pix.samples)
    im=im.resize((140,90),Image.Resampling.BILINEAR)
    return im.point(lambda v: 255 if v < 145 else 0)


def discover_same_area_matches(
    doc: pymupdf.Document,
    reference_page: int,
    reference_rect: Sequence[float] | pymupdf.Rect,
    *, min_similarity: float = 0.985,
) -> list[PageMatch]:
    """Search other pages for same embedded image or identical raster appearance.

    Exact image digest + normalized placement are preferred; vector fallback
    requires very similar visible pixels; no OCR or semantic guessing.
    """
    page = doc[reference_page]
    r = _as_rect(reference_rect)
    if not page.rect.contains(r):
        raise ValueError("Markierung liegt außerhalb der Referenzseite.")
    # The user's rectangle is an approximate gesture, not the exact image
    # bounds. Once image content is recognized, use true object bounds.
    contained = [im for im in image_candidates(page, r) if im.get('digest')]
    matches=[]
    ref_mask = None
    for index,target in enumerate(doc):
        if index == reference_page:
            continue
        if target.rotation != page.rotation:
            continue
        proposed = _rel_rect(r,page.rect,target.rect)
        if not target.rect.contains(proposed):
            continue
        # For selected standalone images: match all selected image digests AND
        # their relative placement, size, so repeated unrelated images elsewhere
        # are not targeted.
        if contained:
            images=target.get_image_info(xrefs=True)
            found=[]
            for original in contained:
                ob=pymupdf.Rect(original['bbox'])
                expected = _rel_rect(ob,page.rect,target.rect)
                for im in images:
                    bbox=pymupdf.Rect(im['bbox'])
                    if (im.get('digest') == original['digest'] and
                        abs(bbox.x0 - expected.x0) <= 3 and abs(bbox.y0 - expected.y0) <= 3 and
                        abs(bbox.width - expected.width) <= 2 and abs(bbox.height - expected.height) <= 2):
                        found.append(im)
                        break
            if len(found) == len(contained):
                # Propose *exact* image bounds on the target page, not a copy
                # of the operator's possibly too-tight initial rectangle.
                precise = bbox_to_display(target, found[0])
                for im in found[1:]:
                    precise |= bbox_to_display(target, im)
                matches.append(PageMatch(index,precise,'Identisches eingebettetes Bild',1.0))
            continue
        # Visual similarity fallback for repeatable VECTOR artwork on pages.
        # Requires strong, nonempty, image-based evidence; rejects blank regions.
        try:
            if ref_mask is None:
                ref_mask = _crop_signature(page,r)
            if not (ref_mask.getbbox() and ref_mask.histogram()[255] > 120):
                break
            target_mask = _crop_signature(target,proposed)
            d = ImageChops.difference(ref_mask, target_mask)
            changed = d.histogram()[255]
            total_pixels = float(ref_mask.width * ref_mask.height)
            foreground_before = ref_mask.histogram()[255]
            foreground_after = target_mask.histogram()[255]
            # Jaccard foreground overlap rejects a changed/missing logo even
            # when a large surrounding rectangle is mostly white.
            intersect = (foreground_before + foreground_after - changed) / 2.0
            union = (foreground_before + foreground_after + changed) / 2.0
            iou = (intersect / union) if union else 0.0
            difference_fraction = changed / total_pixels
            if 1.0 - difference_fraction >= min_similarity and iou >= 0.97:
                matches.append(PageMatch(index, proposed, 'Gleiches sichtbares Muster', min(iou, 1.0-difference_fraction)))
        except (ValueError,RuntimeError):
            continue
    return matches
