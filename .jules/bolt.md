## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-28 - Single-Pass Depth-First Classification for DOM Selector Hierarchies
**Learning:** Sequential multi-pass tree traversals for ordered CSS/tag selectors (e.g. evaluating 9 DOM selectors via `_find_nodes`) re-walk the entire DOM tree up to N times. Traversing the DOM tree once to populate priority candidate buckets reduces tree visits from O(K*N) to O(N) and cuts container selection latency by ~60-80%.
**Action:** When searching DOM trees for priority-ordered container elements or rules, use a single-pass classification walk to collect candidates into priority buckets before evaluating them.
