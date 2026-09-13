## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-13 - Attribute-less Fast-Paths in Recursive DOM Node Serialization & Filtering
**Learning:** Evaluated attributes and generator expression formatting on every node in recursive DOM tree serialization creates significant object allocation and call overhead, even though the vast majority of semantic HTML tags (e.g. `<p>`, `<span>`, `<b>`, `<i>`, `<ul>`, `<li>`) have empty attributes dicts (`not node.attrs`). Checking `if not node.attrs:` early yields a ~1.8x (45%) speedup in DOM serialization and noise filtering.
**Action:** When performing recursive AST or DOM tree traversals, check for empty metadata/attributes dicts (`if not node.attrs:`) to bypass generator/dict comprehension allocations.
