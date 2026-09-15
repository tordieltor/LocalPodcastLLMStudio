## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-15 - Single-Pass Bucket Sorting for Multi-Rule DOM Tree Selection
**Learning:** Running N sequential recursive tree traversals to find nodes matching ordered priority selectors scales as O(N * size(tree)). Single-pass depth-first traversal bucketing nodes by priority index reduces tree visits to O(1 * size(tree)), yielding ~10-11x speedups on large DOM trees while preserving exact selection semantics and method encapsulation.
**Action:** When evaluating multiple hierarchical priority predicates over custom tree structures, traverse the tree once to populate priority buckets instead of executing repeated full-tree scans.
