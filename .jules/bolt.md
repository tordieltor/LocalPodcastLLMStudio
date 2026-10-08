## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-08 - Pre-computed O(1) Lookup Table for MPEG Frame Parsing
**Learning:** Recomputed bitwise arithmetic, range checks, and dictionary lookups across tens of thousands of binary MP3 frame headers in pure Python create significant CPU overhead. Indexing header bytes 1 and 2 directly into a 64KB pre-computed tuple (`(b1 << 8) | b2`) converts per-frame header parsing into an instant O(1) array lookup (~1.79x faster audio stitching).
**Action:** For fixed-width binary header fields with bounded bit fields (e.g. 16-bit header masks), pre-compute valid frame specifications at module import time into an immutable lookup tuple.
