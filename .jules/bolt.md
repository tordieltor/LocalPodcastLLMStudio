## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-01 - CPython C-Level Search Optimization in `str.replace`
**Learning:** In CPython, `str.replace` and compiled `re.sub` already execute C-level search loops and return original string references immediately when target patterns are absent. Pre-checking fixed single-character substrings in Python bytecode (`if '“' in s:`) adds redundant interpreter passes. Fast-path guards are only beneficial when substituting complex regex patterns with simple fixed token guards (like `'-\n' in text`).
**Action:** Do not wrap simple `str.replace` calls with `if substring in s:` checks; rely on CPython's C implementation.
