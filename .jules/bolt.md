## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-03 - Reverse Piece List Inspection to Avoid Quadratic String Joining
**Learning:** Calling `"".join(self._pieces)` on an accumulated list of string pieces during parser callbacks (e.g., `_ensure_newlines` on HTML tags) creates quadratic O(N^2) string allocations as document size grows. Inspecting `self._pieces` in reverse order (`reversed(self._pieces)`) checks trailing character invariants in O(1) time without joining the buffer.
**Action:** When inspecting trailing state on list-based string builders, iterate backwards over the list elements instead of joining the entire list on every element callback.
