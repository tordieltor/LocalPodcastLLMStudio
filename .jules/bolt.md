## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-22 - Fast-path Canonical String Equality Checks
**Learning:** Calling memoized normalization functions or LRU-cached helpers in high-frequency loop iterations still incurs wrapper function call and cache lookup overhead (~200ms per 100k calls). Short-circuiting canonical strings (e.g. `if speaker == "Host 1"`) with direct equality checks reduces iteration overhead by ~85% (~6.9x speedup).
**Action:** Add direct equality fast-paths for expected canonical string values before delegating to LRU-cached or regex-based normalization functions.
