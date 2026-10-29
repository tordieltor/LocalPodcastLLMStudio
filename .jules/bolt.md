## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-29 - Single-Pass Bucket Priority Traversals and Short-Circuit DOM Counting
**Learning:** Evaluating multi-tier selector lists by running repeated full-tree traversals (e.g. 9 separate DFS calls) and calling full DOM text string joins (`get_text_content()`) creates quadratic traversal and string allocation overhead. Using a single-pass tree traversal into priority buckets and a short-circuit non-whitespace character counter (`_has_min_text_length`) reduces container selection time by up to 4.5x and text validation by ~300x.
**Action:** In DOM tree analysis, group selector criteria into a single-pass priority bucket walk and short-circuit subtree length checks as soon as the threshold is met instead of concatenating full subtree text.
