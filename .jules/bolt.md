## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-07 - Refine Regex Character Ranges to Exclude Valid Whitespace
**Learning:** Broad character range regexes like `[\x00-\x1f]` match valid ASCII whitespace (`\n`, `\r`, `\t`), triggering callback lambdas on every newline/tab in formatted LLM text even when no sanitization is required. Excluding `\r\n\t` from the character range (`[\x00-\x08\x0b\x0c\x0e-\x1f]`) and guarding with `.search()` bypasses regex matches on valid text completely.
**Action:** Exclude valid formatting whitespace from control-character regexes and guard `.sub()` invocations with `.search()`.
