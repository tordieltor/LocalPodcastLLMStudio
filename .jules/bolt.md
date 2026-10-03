## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-03 - 64KB Lookup Table for Binary MP3 Header Length Parsing
**Learning:** Parsing 4-byte MPEG Layer III frame headers in pure Python via per-frame bit-shifting, tuple indexing, and arithmetic recalculation dominates binary audio stream scanning overhead. Precomputing base frame lengths for all 65,536 2-byte header combinations `(b1 << 8) | b2` into a static 64KB flat array reduces per-frame header parsing cost by ~31%.
**Action:** For fixed binary header protocol specifications (e.g., MP3, WAV, FLAC frame headers), precompute frame property calculations into flat array lookup tables indexed by header bit combinations.
