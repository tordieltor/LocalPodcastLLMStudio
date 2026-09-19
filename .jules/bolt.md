## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-19 - Fast-Path Canonical Speaker Guard Before String Normalization
**Learning:** Calling `.lower().strip()` and dictionary/LRU cache lookups on every speaker normalization invocation creates millions of temporary string allocations when normalizing canonical speaker strings ('Host 1', 'Host 2'). Adding a direct equality guard (`if raw_speaker == "Host 1" or raw_speaker == "Host 2": return raw_speaker`) avoids string allocations and dictionary lookups entirely (~2.35x speedup / 58% reduction in runtime).
**Action:** Fast-path exact canonical string matches before executing lowercasing, stripping, or dict/cache lookups in high-throughput string normalization loops.
