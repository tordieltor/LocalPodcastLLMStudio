## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-16 - Single-Pass Bucket Categorization for Priority Tree Selectors
**Learning:** Running N separate tree-traversal queries across a large DOM or AST tree to evaluate hierarchical selector priorities scales quadratically with tree size and selector count. Collecting candidate nodes into priority buckets during a single depth-first walk, combined with memoized sub-tree string serialization, reduces tree scanning from O(N_selectors * N_nodes) to O(N_nodes).
**Action:** When searching tree structures for prioritized node predicates, collect candidate matches into bucket arrays in a single depth-first traversal before evaluating selection rules and text extractions.
