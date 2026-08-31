## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-08-31 - Fast-Path Constant Frame Size Validation in Pure Python Audio Streams
**Learning:** In pure Python audio stream extractors, parsing headers, verifying layers/sampling rates, and doing dictionary lookups for every single frame in a multi-megabyte MP3 payload introduces significant CPU overhead even when segment slicing is optimized. For synthetic TTS streams (e.g. Edge-TTS) where frames are uniform and clean, validating frame sync words via a stride loop first allows returning the buffer directly (~85% time reduction).
**Action:** Always attempt a fast stride validation loop over uniform binary frame streams before falling back to full per-element header decoding.
