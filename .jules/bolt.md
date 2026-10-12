## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-12 - Single-Pass DOM Container Selection in HTML Extraction
**Learning:** Executing multiple full-tree DFS traversals for ordered CSS/tag selectors on DOM trees creates O(K*N) node visits and redundant `get_text_content()` string concatenations. Performing a single-pass DFS stack traversal that classifies nodes into priority buckets and computes candidate text lengths once reduces tree visits by up to 90% (~10.4x speedup).
**Action:** When evaluating ordered hierarchy rules over DOM or AST trees, collect candidates into prioritized buckets in a single DFS pass before selecting the optimal node.
