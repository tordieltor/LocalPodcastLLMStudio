## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-28 - Single-Pass Bucket Classification for Hierarchical Tree Selectors
**Learning:** Executing multiple separate DOM tree traversals (`_find_nodes`) for ordered container selector evaluation causes O(K * N) node visits and redundant `get_text_content()` calculations. Classifying nodes into rank buckets during a single depth-first walk (`_walk`) reduces traversals from O(K * N) to O(N) (~4.4x speedup).
**Action:** In DOM or AST tree search pipelines with ordered selector priorities, collect candidate nodes into prioritized rank buckets during a single tree traversal rather than executing sequential search passes.
