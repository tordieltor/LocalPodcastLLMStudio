## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-05 - Iterative Stack-based DOM Traversal Prevents Stack Overflows
**Learning:** Recursive DOM tree traversals (`get_text_content`, `_find_nodes`, `serialize_node`) hit Python's recursion limit (1000) on deeply nested HTML pages (e.g. deep container/div wrappers). Replacing recursive calls with explicit stack loops eliminates call stack allocation overhead and prevents `RecursionError` crashes during HTML extraction.
**Action:** Use explicit iterative stack loops `(node, entering)` for DFS traversal and serialization of DOM tree structures in pure Python HTML parsing modules.
