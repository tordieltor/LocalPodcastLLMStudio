## 2026-03-31 - Memoizing Frequently Called Pure String Normalizers in Hot Loops

**Learning:** `normalize_speaker` is called repeatedly across parser tiers and TTS audio synthesis iterations for every single dialogue turn in a podcast episode. Because the set of raw speaker inputs is small (e.g., 'Host 1', 'Host 2', 'Kari', 'Ola', 'Jenny', 'Guy') but called tens of thousands of times during transcript processing and synthesis, adding `@lru_cache(maxsize=128)` yields a ~11x speedup (from 0.86s to 0.07s for 400k calls) with minimal memory footprint.

**Action:** Look for pure function string/value normalization routines in core parsing or pipeline utilities that receive repeated discrete values and wrap them in `@lru_cache`.
