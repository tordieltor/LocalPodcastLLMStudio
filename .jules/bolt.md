## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-21 - Single-Pass Priority Bucket Traversal for DOM Container Selection
**Learning:** Evaluating multiple semantic container selectors via separate `_find_nodes` Depth-First Searches causes up to 9 redundant full-tree passes ($O(K \cdot N)$ depth-first traversals). Replacing multi-pass DFS with a single-pass iterative stack traversal using priority buckets reduces DOM tree passes to 1 (~4.5x speedup) while eliminating stack overflow risks on deeply nested HTML trees.
**Action:** When querying hierarchical DOM or AST trees for multiple ordered candidates, collect candidate nodes into priority buckets in a single iterative traversal rather than executing separate tree search passes.
