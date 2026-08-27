## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-27 - Reverse List Inspection over Full String Joining for Trailing Characters
**Learning:** Re-joining a list of accumulator strings (`"".join(pieces)`) to inspect trailing characters (e.g., counting newlines) on every tag boundary in standard/streaming HTML parsers causes O(N^2) memory and allocation overhead. Reverse-iterating the pieces list and stripping trailing characters per piece gives O(1) trailing character count.
**Action:** Inspect string buffer list tails from right-to-left instead of re-joining full lists when validating whitespace or newline counts in streaming parsers.
