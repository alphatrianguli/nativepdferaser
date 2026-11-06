"""Conservative PDF content-stream surgery for isolated CAD vector path blocks.

Only deletes independently scoped path drawings of the form
  q 1 0 0 1 <x> <y> cm
<path operations>
Q
with no text, images, or nested graphics-state blocks inside.

A path is removed only if its full geometry is inside a marked region and every
eligible path on the selected page is accounted for. Otherwise returns None and
the legacy native engine is used. All untouched drawing/text commands are kept.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

import pymupdf

_NUM = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
_NUMBER = re.compile(_NUM + rb"\Z")
_BLOCK = re.compile(
    rb"(?ms)^q[ \t]+1[ \t]+0[ \t]+0[ \t]+1[ \t]+"
    rb"(?P<x>" + _NUM + rb")[ \t]+(?P<y>" + _NUM + rb")[ \t]+cm[ \t]*\r?\n"
    rb"(?P<body>.*?)^Q[ \t]*(?:\r?\n|$)"
)
_PAINT = {b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_OTHER = {b"h", b"n"}


def _path_bbox(m: re.Match[bytes], page: pymupdf.Page) -> pymupdf.Rect | None:
    """Return a conservative full bbox or None when the block is not provably path-only."""
    tokens = m.group("body").split()
    points: list[pymupdf.Point] = []
    xoff = float(m.group("x"))
    yoff = float(m.group("y"))
    pt_matrix = page.transformation_matrix
    paint_count = 0
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and _NUMBER.fullmatch(tokens[j]):
            j += 1
        if j == len(tokens):
            return None
        op, nums = tokens[j], tokens[i:j]
        if op in (b"m", b"l") and len(nums) == 2:
            local_points = [(float(nums[0]), float(nums[1]))]
        elif op == b"c" and len(nums) == 6:
            local_points = [(float(nums[k]), float(nums[k+1])) for k in (0,2,4)]
        elif op == b"re" and len(nums) == 4:
            x,y,w,h = [float(n) for n in nums]
            local_points = [(x,y),(x+w,y+h)]
        elif op in _PAINT | _OTHER and not nums:
            if op in _PAINT:
                paint_count += 1
            local_points = []
        else:
            return None
        for px,py in local_points:
            points.append(pymupdf.Point(xoff+px,yoff+py) * pt_matrix)
        i = j + 1
    if not points or paint_count != 1:
        return None
    return pymupdf.Rect(
        min(p.x for p in points), min(p.y for p in points),
        max(p.x for p in points), max(p.y for p in points),
    )


def try_surgical_removal(
    doc: pymupdf.Document, selections: Mapping[int, Sequence[pymupdf.Rect]],
) -> dict[int, int] | None:
    """Try exact command removal; modify doc only after every page is supported.

    Returns deleted path counts per page, or None for unsupported PDFs.
    Does not modify the page's text instructions or graphics outside marked areas.
    """
    modifications: list[tuple[list[int], bytes]] = []
    removed_counts: dict[int, int] = {}
    for idx, rectangles in selections.items():
        page = doc[idx]
        if page.rotation != 0:
            return None  # Restrict first release to unrotated pages.
        content_refs = page.get_contents()
        if not content_refs:
            return None
        combined = b"\n".join(doc.xref_stream(x) for x in content_refs)
        eligible = sum(
            any(rect.contains(pymupdf.Rect(dr["rect"])) for rect in rectangles)
            for dr in page.get_drawings()
        )
        if eligible == 0:
            return None
        ranges = []
        for m in _BLOCK.finditer(combined):
            bbox = _path_bbox(m, page)
            if bbox is not None and any(rect.contains(bbox) for rect in rectangles):
                ranges.append((m.start(), m.end()))
        # If the file also has eligible artwork in a different representation,
        # don't partially remove it; a different engine must handle this page.
        if len(ranges) != eligible:
            return None
        remaining = []
        cursor = 0
        for a,b in ranges:
            remaining.append(combined[cursor:a])
            cursor = b
        remaining.append(combined[cursor:])
        modifications.append((content_refs, b"".join(remaining)))
        removed_counts[idx] = len(ranges)

    # Commit only after all pages have passed the conservative structural test.
    for refs,new_content in modifications:
        doc.update_stream(refs[0], new_content, compress=True)
        for xref in refs[1:]:
            doc.update_stream(xref, b"\n", compress=False)
    return removed_counts
