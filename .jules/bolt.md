## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-01 - Avoid Accumulative List Joins in Streaming Parsers
**Learning:** Calling `''.join(self._pieces)` inside element handlers (such as tag boundary whitespace/newline formatters) causes quadratic O(N^2) string allocations as the piece array grows. Inspecting list elements in reverse (`for piece in reversed(self._pieces):`) calculates trailing line endings in O(1) amortized time.
**Action:** In streaming parsers or string builders, never join accumulated buffer arrays repeatedly to inspect state; inspect the end of the list directly in reverse.
