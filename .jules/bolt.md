## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-02 - Deferring Attribute Dictionary Comprehensions in HTML Parsers
**Learning:** In streaming `HTMLParser` callbacks (`handle_starttag`), building dictionary comprehensions `{k.lower(): (v or "") for k, v in attrs}` for every HTML element creates thousands of short-lived dict allocations when target attributes (like `href` on `<a>` tags) are only needed for specific tags. Deferring attribute extraction to tag-specific branches avoids per-element allocation overhead on large documents.
**Action:** In `HTMLParser` handlers, iterate `attrs` lazily or construct attribute dicts conditionally only inside tag-specific branches where attributes are actually consumed.
