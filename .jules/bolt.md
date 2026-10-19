## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-19 - Single-Pass Priority Bucketing in DOM Container Selection
**Learning:** Evaluating CSS selector hierarchies against DOM trees by running sequential full-tree walks (`_find_nodes`) causes up to N_selectors full-tree traversals and redundant recursive text extractions. Traversing the DOM tree once and placing candidate nodes into priority buckets reduces tree traversals to O(1) pass (~10.9x speedup).
**Action:** When matching hierarchical DOM or AST rules, categorize nodes into priority buckets during a single tree pass instead of running multiple search passes.
