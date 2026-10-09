## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-09 - Pre-computed Class Token Sets & Iterative DOM Traversal
**Learning:** Splitting class strings and evaluating generator comprehensions repeatedly in DOM node queries creates substantial overhead during HTML parsing. Pre-computing lowercased class token sets on `DOMNode` initialization speeds up class membership checks by ~7.7x. Additionally, replacing recursive DOM tree traversal in `get_text_content()` with iterative stack processing eliminates Python recursion stack allocations and prevents `RecursionError` on deep DOM trees.
**Action:** Pre-compute token sets in `__slots__` data structures when performing frequent membership checks during AST/DOM queries, and prefer explicit iterative stack loops over recursion for tree traversals.
