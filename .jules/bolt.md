## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-27 - Tuple Substring Loop Guards vs Compiled Regex Search
**Learning:** Checking a large tuple of candidate keywords in Python with `any(k in s for k in keyword_tuple)` introduces Python-level iteration and generator overhead that can be slower than compiled C regex engine execution (`re.search`) when the tuple is large (>20 elements). Single or small-tuple substring checks (`if 'foo' in s:`) are fast, but large tuple loops in Python should be benchmarked against `re.search`.
**Action:** Use fast single-string or small-set substring checks for guards; avoid long tuple `any()` loops in hot paths where C-compiled `re.search` is already optimized.
