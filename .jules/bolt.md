## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-18 - Single-Pass Bucket Classification for Tree Container Selection
**Learning:** Evaluating K sequential selector queries on hierarchical DOM trees causes up to K separate full depth-first traversals (O(K * N)), repeatedly splitting attributes and checking classes. Collecting candidate nodes into priority buckets in a single depth-first walk reduces complexity to O(N) and yields an order-of-magnitude speedup (~13x).
**Action:** When evaluating multiple prioritized CSS/tag selectors on custom DOM trees, collect candidate nodes in a single tree traversal using indexed priority buckets rather than executing repeated `_find_nodes` tree traversals.
