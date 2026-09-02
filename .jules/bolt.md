## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-02 - Pre-computed Noise Flags and Set Lookups for DOM Node Filtering
**Learning:** Repeatedly checking regex noise patterns (`NOISE_ATTR_PATTERN.search`) and splitting class attribute strings during DOM tree traversals adds substantial overhead across thousands of nodes. Since DOMNode attributes are static once parsed, computing `class_set: set[str]` and `is_noise: bool` during `__init__` replaces O(N) regex searches and string splits with O(1) set/boolean attribute lookups.
**Action:** Pre-compute immutable properties (like class sets or noise classifications) on tree nodes upon creation rather than evaluating them lazily or repeatedly during recursive graph traversals.
