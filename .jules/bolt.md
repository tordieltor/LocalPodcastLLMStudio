## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-21 - Version-Separated Pre-Filtered Non-Standard CIDR Tuples in IP Validation
**Learning:** Checking public IP addresses against a flat list of CIDR networks causes redundant containment checks for standard ranges already evaluated by `ipaddress` boolean properties (`is_private`, `is_loopback`, `is_link_local`, etc.) as well as cross-version comparisons. Pre-filtering non-standard CIDR rules into separated IPv4 and IPv6 tuples cuts containment checks from 21 down to 7 (IPv4) or 1 (IPv6), achieving a ~3.5x speedup.
**Action:** When validating IP addresses against CIDR block lists in SSRF or network filters, pre-filter non-standard networks by IP version and exclude ranges covered by standard address properties.
