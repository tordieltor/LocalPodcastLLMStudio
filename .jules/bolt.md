## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-30 - Fast-Path Header Cache for MP3 Frame Parsing
**Learning:** Re-parsing MPEG Audio Layer III frame headers (decoding bitrate, sampling rate, version, layer, and integer division for frame length) on every frame in continuous binary streams causes significant function call and arithmetic overhead (~0.7s per 5,000 frames). Memoizing normalized header configurations (`(b1 << 8) | (b2 & 0xFD)`) for contiguous audio frames reduces parsing overhead by ~2.9x (~0.24s).
**Action:** When scanning repetitive binary headers in streams, compare normalized header configuration bytes (`b1_b2_norm`) against the previous frame to reuse computed frame lengths with zero arithmetic overhead.
