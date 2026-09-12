## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-24 - Python Generator Iteration vs Compiled C-Regex Search
**Learning:** Attempting to guard regex execution with pure Python generator loops (`any(ord(c) < 32 ... for c in s)`) is ~4x slower than directly calling compiled C-regex search (`re.search`). Pure C string checks (e.g. `'[' in s` or `' ' in s`) are ultra-fast, but character-by-character Python bytecode loops incur heavy interpreter overhead.
**Action:** Only use fast single-token/substring `in` checks for fast-path regex guards; use `pattern.search()` rather than Python `for` loops when scanning for character ranges or sets.
