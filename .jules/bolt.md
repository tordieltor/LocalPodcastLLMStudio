## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-14 - Exclude Standard Whitespace Characters from Control Character Regex Ranges
**Learning:** Compiling control character regexes as `r"[\x00-\x1f]"` matches standard whitespace characters (`\n`=0x0a, `\r`=0x0d, `\t`=0x09) present in formatted JSON strings. Excluding standard whitespace from the range (`r"[\x00-\x08\x0b\x0c\x0e-\x1f]"`) allows `regex.search()` to return `None` on clean multi-line JSON, avoiding unnecessary regex substitution passes and lambda invocations.
**Action:** Exclude standard whitespace characters (`\n`, `\r`, `\t`) from control character regex patterns when processing multi-line structured text formats like JSON.
