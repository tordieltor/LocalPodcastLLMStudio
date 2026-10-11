## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-11 - Single-pass DFS Bucket Classification for DOM Container Selection
**Learning:** Running 9 sequential DFS tree traversals over DOM trees to evaluate candidate element selectors created O(9 * N_nodes) overhead, taking over 5.4s for deep/complex HTML documents when early priority tags were absent. A single-pass DFS traversal that classifies nodes into priority bucket lists reduces traversal overhead to O(N_nodes), speeding up container selection by ~8x (~540ms down to ~69ms).
**Action:** When scanning HTML DOM trees for hierarchical semantic selectors, use a single DFS pass with priority bucket lists rather than multiple full tree scans.
