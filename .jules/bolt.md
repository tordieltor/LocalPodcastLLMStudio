## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-05 - Avoid Full String Join in Streaming Parser Trailing Character Checks
**Learning:** Calling `"".join(chunks)` to inspect trailing characters (e.g. counting trailing newlines in `HTMLToMarkdownParser`) turns local tag whitespace checks into an O(N) allocation per tag, leading to O(N^2) complexity overall for large HTML documents. Iterating backwards through accumulated chunks directly avoids intermediate string joins.
**Action:** In streaming parsers accumulating list chunks, iterate backwards through `reversed(chunks)` to inspect or count suffix characters instead of creating joined string copies.
