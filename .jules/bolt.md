## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-19 - Fast Bitwise CBR Validation in MP3 Audio Extraction
**Learning:** Executing full MPEG header decoding with dictionary lookups and integer divisions on every frame in contiguous CBR MP3 streams creates significant CPU overhead (~14.6ms per 1.8MB file). Pre-calculating base frame length from initial header and validating sync bytes (`0xFF`, `b1`, `b2 & 0xFD`) directly in pure Python speeds up frame extraction by ~3.3x (~4.4ms per 1.8MB file).
**Action:** When scanning homogeneous binary audio streams (MP3/PCM), extract stream configuration once from the initial header and validate subsequent frames via bitwise mask checks.
