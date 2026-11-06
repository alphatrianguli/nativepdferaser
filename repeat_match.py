"""High-confidence, same-position discovery of repeated PDF image, text and vector content.

Matching produces suggestions only; never deletes objects or edits pages.
For text, compare normalized character-independent PDF word tokens within a small
area at a corresponding position. For images, use identity hashes. For vector
art, use the conservative visual matcher from the previous release.
"""
from __future__ import annotations

import unicodedata
from typing import Sequence

import pymupdf

from engine import _page_coords
from image_selection import image_candidates
from match_pages import PageMatch, discover_same_area_matches, _rel_rect


def _midpoint_inside(rect: pymupdf.Rect, word: tuple) -> bool:
    return rect.contains(pymupdf.Point((word[0] + word[2]) / 2, (word[1] + word[3]) / 2))


def _words_in(page: pymupdf.Page, display: pymupdf.Rect) -> list[tuple]:
    local = _page_coords(page, display)
    words = [w for w in page.get_text('words', sort=False) if _midpoint_inside(local, w)]
    # PDF content order is not necessarily visual order. This is stable for
    # repeated text, without matching arbitrary words at other locations.
    words.sort(key=lambda w: (round(w[1] / 3), round(w[0] / 3), w[5], w[6], w[7]))
    return words


def _tokens(words: list[tuple]) -> tuple[str, ...]:
    return tuple(unicodedata.normalize('NFKC', str(w[4])).strip() for w in words)


def _eligible_text(tokens: tuple[str, ...]) -> bool:
    meaningful = ''.join(c for w in tokens for c in w if c.isalnum())
    # Avoid auto-selecting unrelated page numbers, drawing-grid coordinates,
    # revision letters or single-character technical annotations.
    return bool(tokens) and len(meaningful) >= 5 and len(tokens) <= 25


def discover_same_text_matches(doc: pymupdf.Document, ref_index: int,
                               display_rect: Sequence[float] | pymupdf.Rect,
                               *, tolerance: float = 5.0) -> list[PageMatch]:
    """Match actual PDF text, token for token, at the same relative position.

    This is *not* OCR and cannot match text converted into vector outlines.
    It deliberately avoids fuzzy matching to prevent removing another name.
    """
    ref_page = doc[ref_index]
    ref = pymupdf.Rect(display_rect)
    if not ref_page.rect.contains(ref):
        raise ValueError('Der markierte Bereich liegt außerhalb der Seite.')
    ref_words = _words_in(ref_page, ref)
    signature = _tokens(ref_words)
    if not _eligible_text(signature):
        return []
    results: list[PageMatch] = []
    for target_index, target in enumerate(doc):
        if target_index == ref_index or target.rotation != ref_page.rotation:
            continue
        expected = _rel_rect(ref, ref_page.rect, target.rect)
        # Compare each actual PDF word near its corresponding source position.
        # This avoids accidentally including adjacent table-cell labels in an
        # expanded search box (a common case in engineering title blocks).
        padding = min(max(tolerance, target.rect.width * 0.005), 9.0)
        all_target_words = target.get_text('words', sort=False)
        sx = target.rect.width/ref_page.rect.width
        sy = target.rect.height/ref_page.rect.height
        used: set[int] = set()
        matched: list[tuple] = []
        for source in ref_words:
            name = unicodedata.normalize('NFKC', str(source[4])).strip()
            source_x=(source[0]+source[2])/2 * sx
            source_y=(source[1]+source[3])/2 * sy
            candidates=[]
            for idx, word in enumerate(all_target_words):
                if idx in used or unicodedata.normalize('NFKC',str(word[4])).strip()!=name:
                    continue
                dx=(word[0]+word[2])/2 - source_x
                dy=(word[1]+word[3])/2 - source_y
                if abs(dx) <= padding and abs(dy) <= padding:
                    candidates.append((dx*dx+dy*dy, idx, word))
            if not candidates:
                matched=[]
                break
            _, chosen_idx, chosen_word = min(candidates, key=lambda v:v[0])
            used.add(chosen_idx)
            matched.append(chosen_word)
        if len(matched)!=len(ref_words) or _tokens(matched)!=signature:
            continue
        # Only select the proven matching word boxes, padded slightly so
        # adjacent text and table titles are not included on the target page.
        local=pymupdf.Rect(matched[0][:4])
        for word in matched[1:]:
            local |= pymupdf.Rect(word[:4])
        local=pymupdf.Rect(local.x0-.75,local.y0-.75,local.x1+.75,local.y1+.75)
        displayed=pymupdf.Rect(local * target.rotation_matrix) & target.rect
        # Extra guard against a mismatched word at the edge of the tolerance.
        if not displayed.intersects(expected):
            continue
        results.append(PageMatch(target_index, displayed, 'Identischer PDF-Text', 1.0))
    return results


def discover_repeated_elements(doc: pymupdf.Document, ref_index: int,
                               display_rect: Sequence[float] | pymupdf.Rect,
                               *, removal_mode: str='intelligent') -> list[PageMatch]:
    """Dispatch by content type, with no implicit page modifications."""
    reference = pymupdf.Rect(display_rect)
    page = doc[ref_index]
    if removal_mode == 'text_only':
        return discover_same_text_matches(doc, ref_index, reference)
    if removal_mode == 'image_only':
        return discover_same_area_matches(doc, ref_index, reference) if image_candidates(page, reference) else []
    if removal_mode == 'precision':
        # In vector-only mode, don't propose an image or text as a vector logo.
        if image_candidates(page, reference) or _words_in(page, reference):
            return []
        return discover_same_area_matches(doc, ref_index, reference)
    if image_candidates(page, reference):
        return discover_same_area_matches(doc, ref_index, reference)
    if _words_in(page, reference):
        return discover_same_text_matches(doc, ref_index, reference)
    return discover_same_area_matches(doc, ref_index, reference)
