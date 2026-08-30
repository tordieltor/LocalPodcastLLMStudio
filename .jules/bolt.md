## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-30 - Single-Pass Bucket Traversal for Multi-Selector DOM Extraction
**Learning:** Running sequential DFS tree traversals over a DOM tree for multiple priority selectors performs up to K redundant tree traversals. Bucketing nodes into priority slots during a single DFS traversal reduces node visits from O(K * N) to O(N) and yields a ~10x speedup on DOM container selection.
**Action:** Replace sequential multi-pass tree searches with a single-pass `_walk` function that populates ordered priority buckets.
