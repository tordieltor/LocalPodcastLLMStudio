## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-07 - Single-Pass Multi-Predicate Bucket Traversal in DOM Container Selection
**Learning:** Performing multiple sequential depth-first searches over a DOM tree for separate CSS/tag selectors (e.g. 9 full tree walks in `select_primary_container`) causes redundant $O(S \cdot N)$ traversal overhead. Collecting nodes into prioritized selector buckets in a single iterative tree traversal reduces work to $O(N)$ and avoids stack overflow risks on deep trees.
**Action:** When searching DOM trees or ASTs for a prioritized list of element selectors, traverse the tree once with an explicit stack and categorize matching nodes into bucket lists by selector priority.
