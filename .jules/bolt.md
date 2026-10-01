## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-01 - O(1) Precomputed Lookup Tables for 2-Byte MP3 Header Parsing
**Learning:** Re-parsing 4-byte MPEG frame headers in pure Python with bit-shifts, dictionary queries, and integer division for tens of thousands of frames adds significant runtime overhead (~580 ms / 500k frames). Indexing a 64K lookup table by `(b1 << 8) | b2` reduces header frame length parsing to a single array access, providing a ~1.93x throughput speedup (~307 ms / 500k frames).
**Action:** For binary header parsing where 16 bits fully determine length/validity, precompute a 65,536-element array at module load time to replace per-frame mathematical decoding with O(1) direct array lookups.
