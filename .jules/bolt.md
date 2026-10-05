## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-05 - Single-Pass Bucket Traversal for Multi-Selector DOM Matching
**Learning:** Querying a custom lightweight DOM tree with a list of N priority predicate selectors by executing N separate full-tree depth-first traversals scales as O(N * M) where M is the number of DOM nodes. Collecting candidate nodes into N priority buckets during a single depth-first walk reduces node visits from N * M to M (~13x throughput increase).
**Action:** When matching hierarchical priority rules against tree structures in pure Python, collect candidates across all priority tiers during a single tree pass rather than re-traversing the tree for each rule.
