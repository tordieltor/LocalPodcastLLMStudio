## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-23 - Short-Circuit Subtree Traversal for Threshold Text Validation
**Learning:** Concatenating full DOM subtree text via `"".join(...)` to check string length (`len(text) > N`) allocates large temporary strings across hundreds of nodes. An iterative stack traversal that exits as soon as `min_len` non-whitespace characters are counted short-circuits execution (~96x speedup).
**Action:** Use counting stack traversals with early termination when validating minimum length thresholds on tree or nested structures instead of full string concatenations.
