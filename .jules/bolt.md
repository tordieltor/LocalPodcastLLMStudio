## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-10-27 - Precomputed O(1) Header Look-Up Tables for Binary Stream Scanning
**Learning:** Bitwise parsing, tuple indexing, dictionary lookups, and integer arithmetic per MP3 frame header in binary audio stitching loop creates significant bottleneck when processing thousands of audio frames. Precomputing a 65,536-entry Look-Up Table (`_FRAME_LEN_LUT`) for 2-byte header combinations at module load time turns frame length parsing into an $O(1)$ index lookup.
**Action:** For binary protocol/stream frame parsing with bounded multi-byte header states (such as MPEG audio header bytes `b1` and `b2`), precalculate valid frame properties into a lookup table.
