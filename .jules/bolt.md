## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-28 - O(1) Set-Lookup Fast Path for Exact Persona String Matching
**Learning:** Linear substring matching over tuples of persona strings (`any(k in s for k in _HOST_1_SPECIFIC)`) creates significant CPU overhead when processing thousands of dialogue turns. Adding O(1) exact set-lookup checks (`if s in _HOST_1_EXACT_SET`) before the linear substring loop yields ~2.1x speedup while preserving LRU cache fallback.
**Action:** Pre-build `set` lookup tables for exact string matches before performing linear sequence/substring checks in hot normalization loops.
