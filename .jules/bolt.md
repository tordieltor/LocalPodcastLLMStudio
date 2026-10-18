## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-18 - Fast-path Tag Probes Before Multi-Selector DOM Traversals
**Learning:** Unconditionally evaluating complex class attributes across every DOM node in a single-pass tree traversal can regress performance compared to tag-only searches because `has_class()` string parsing overhead dominates. Combining an initial fast-path probe for top semantic tags (`<article>`, `<main>`) with a single-pass priority-bucket search for remaining selectors achieves minimal latency across both top-semantic and fallback web pages (~3.3x speedup on fallbacks).
**Action:** Probe high-frequency simple tag criteria first before falling back to multi-attribute or class-parsing tree traversals.
