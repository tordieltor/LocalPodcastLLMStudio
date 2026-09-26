## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-26 - Single-Pass Candidate Bucket Collection in DOM Tree Selection
**Learning:** Performing multiple sequential depth-first searches over a DOM tree for container selection (e.g., searching separately for `article`, `main`, `#mw-content-text`, etc.) results in O(K * N) node visits and redundant string manipulations. Categorizing candidate nodes into priority buckets during a single O(N) depth-first walk eliminates duplicate traversals and string splits.
**Action:** When selecting elements by priority order from custom DOM trees, collect candidate nodes into pre-allocated priority lists during a single tree traversal.
