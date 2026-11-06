"""Conservative removal of stand-alone PDF image drawing commands.

Used only when every occurrence of the underlying image resource is selected.
It removes isolated `q ... cm /Name Do Q` painting blocks and unlinks the
unused page image resource, allowing a full-save garbage sweep to drop its
original bytes. Other page drawing and text operators are untouched.

Nested Form XObjects and more complex rendering programs deliberately return
False; the caller can attempt native redaction under preservation checks.
"""
from __future__ import annotations

from collections import Counter
import re
import pymupdf

_IMAGE_BLOCK = (
    rb'(?<![A-Za-z0-9/_])q[ \t\r\n]+'
    rb'(?:/[A-Za-z0-9_.-]+[ \t\r\n]+(?:ri|gs)[ \t\r\n]+)*'
    rb'(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)[ \t\r\n]+){6}'
    rb'cm[ \t\r\n]+/{name}[ \t\r\n]+Do[ \t\r\n]+Q(?![A-Za-z0-9])'
)


def try_remove_isolated_images(doc: pymupdf.Document, selected: dict[int, list[dict]]) -> bool:
    """Return True if *all* selected image placements can be surgically removed.

    Plans changes before applying any; only supports direct page image resources
    drawn in independent graphics-state blocks. Call on a disposable copy.
    """
    patches = {}  # xref -> (original, new)
    resources = {}  # page index -> names to unlink
    for idx, items in selected.items():
        page = doc[idx]
        all_placements = page.get_image_info(xrefs=True)
        current_counts = Counter(int(v['xref']) for v in items)
        total_counts = Counter(int(v['xref']) for v in all_placements)
        # Avoid editing a page containing unselected placements of a shared xref.
        if any(count != total_counts[xref] for xref, count in current_counts.items()):
            return False
        names_by_xref = {}
        for img in page.get_images(full=True):
            # get_images tuples: (xref, smask, width, height, bpc, colorspace,
            #                       alt, name, filter, parent_xref)
            if len(img) < 10 or img[-1] != 0:
                continue  # nested resource: not a direct page XObject
            xref = int(img[0])
            if xref in current_counts:
                names_by_xref.setdefault(xref, set()).add(str(img[7]))
        if set(names_by_xref) != set(current_counts):
            return False
        if doc.xref_get_key(page.xref, 'Resources')[0] not in ('dict', 'xref'):
            return False
        # Only handle one unambiguous resource name per selected xref here.
        names = {xref: next(iter(n)) for xref, n in names_by_xref.items() if len(n) == 1}
        if len(names) != len(current_counts):
            return False
        matches_by_xref = Counter()
        for stream_xref in page.get_contents():
            data = doc.xref_stream(stream_xref)
            updated = data
            for img_xref, name in names.items():
                pat = re.compile(_IMAGE_BLOCK.replace(b'{name}', re.escape(name.encode('ascii'))))
                updated, n = pat.subn(b' ', updated)
                matches_by_xref[img_xref] += n
            if updated != data:
                if stream_xref in patches and patches[stream_xref][0] != data:
                    return False
                patches[stream_xref] = (data, updated)
        if matches_by_xref != current_counts:
            return False
        resources[idx] = tuple(names.values())

    if not patches:
        return False
    # PDF streams have independent non-incremental save semantics; when a direct
    # resource is unlinked, garbage=4 discards its old image data from the output.
    for xref, (_, value) in patches.items():
        doc.update_stream(xref, value)
    for idx, names in resources.items():
        for name in names:
            doc.xref_set_key(doc[idx].xref, f'Resources/XObject/{name}', 'null')
    return True
