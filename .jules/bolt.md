## 2026-03-30 - Contiguous Byte Stream Slicing in MP3 Frame Extraction
**Learning:** Slicing thousands of individual 144-byte frames in Python `bytes` streams creates massive memory allocation and list join overhead. Slicing contiguous spans of valid frames reduces allocations from O(N_frames) to O(N_segments).
**Action:** When scanning binary streams (MP3/PCM/WAV) in pure Python, track contiguous valid index spans (`seg_start` to `idx`) rather than slicing per element/frame.

## 2026-08-23 - Fast-path Substring Guards Before Regex Executions
**Learning:** Executing compiled C-regex substitution methods (e.g., `_RE_HYPHEN_BREAK.sub`) on large text strings incurs noticeable invocation overhead even when the target pattern is absent. Checking substring presence first in pure C Python (`if '-\n' in text:`) avoids expensive regex engine invocations.
**Action:** Guard string regex replacements with fast `in` substring checks when target tokens are sparse/absent in the vast majority of input documents.

## 2026-09-02 - Avoid Caching Tkinter/CustomTkinter GUI Font Objects Across Lifecycles
**Learning:** Caching `ctk.CTkFont` instances using `@lru_cache` retains references to the underlying Tcl interpreter. When Tk root windows are destroyed and recreated (e.g., across unit test runs or app window restarts), stale font references cause `_tkinter.TclError: invalid command name "font"`.
**Action:** Do not use global `@lru_cache` for Tkinter/CustomTkinter font or widget objects tied to active Tcl interpreter instances.
