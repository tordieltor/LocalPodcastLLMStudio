## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-24 - Single-Pass Priority Bucket Collection for DOM Selection
**Learning:** Performing multiple depth-first traversals over large HTML DOM trees for sequential CSS selector rules incurs O(K*N) overhead. Collecting candidate nodes into priority buckets during a single DFS traversal reduces DOM walks to O(N) while preserving exact selector precedence.
**Action:** When evaluating hierarchical or prioritized node matching rules on tree structures, collect matching nodes into priority buckets in a single pass instead of repeatedly traversing the tree per rule.
