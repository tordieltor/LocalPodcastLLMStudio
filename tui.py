"""
LocalPodcastLLMStudio - Terminal User Interface Launcher Script
Compatibility shim forwarding to `tui.__main__` so `python tui.py`, `python -m tui`,
and `podcast-tui` execute the exact same entry point without package shadowing.
"""

from __future__ import annotations

import sys

from tui.__main__ import TUIApplication, TUIState, bootstrap_state, build_arg_parser, main

__all__ = [
    "TUIApplication",
    "TUIState",
    "bootstrap_state",
    "build_arg_parser",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
