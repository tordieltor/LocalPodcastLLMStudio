## 2026-03-31 - Zero-Copy Offset Inspection for Binary Stream Parsers
**Learning:** Slicing byte buffers (`data[idx:idx+4]`) in high-frequency loops (e.g. 50,000+ MP3 frames per podcast episode) creates excessive short-lived heap allocations. Accepting an optional `offset` parameter in header parsers enables zero-copy in-place inspection and yields ~20%+ faster processing.
**Action:** When parsing contiguous binary frame structures, pass the index/offset into the parser function instead of slicing the buffer.
