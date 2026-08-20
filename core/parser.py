"""
PodcastStudio - Multi-Tier Resilient Dialogue Parser
Converts raw LLM responses into structured List[DialogueTurn] using a 6-tier
fallback pipeline capable of salvaging malformed JSON, markdown fences, syntax errors,
regex object extraction, and plain text transcripts.
"""

import json
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


@dataclass
class DialogueTurn:
    """Represents a single conversational turn in a podcast episode."""
    speaker: str  # Normalized to 'Host 1' or 'Host 2'
    text: str     # Spoken dialogue text

    def to_dict(self) -> Dict[str, str]:
        return {"speaker": self.speaker, "text": self.text}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DialogueTurn":
        speaker = data.get("speaker") or data.get("host") or data.get("name") or data.get("role") or "Host 1"
        text = data.get("text") or data.get("content") or data.get("dialogue") or data.get("line") or ""
        return cls(
            speaker=normalize_speaker(str(speaker)),
            text=str(text).strip()
        )


def normalize_speaker(raw_speaker: str) -> str:
    """
    Normalizes speaker names across Norwegian and English personas:
    Host 1 / Kari / Jenny / Speaker 1 -> 'Host 1'
    Host 2 / Ola / Guy / Speaker 2 -> 'Host 2'
    """
    if not raw_speaker:
        return "Host 1"

    s = raw_speaker.strip().lower()

    # Host 1 patterns
    if any(k in s for k in ["1", "kari", "jenny", "host 1", "host1", "speaker 1", "host_1", "host a"]):
        return "Host 1"

    # Host 2 patterns
    if any(k in s for k in ["2", "ola", "guy", "host 2", "host2", "speaker 2", "host_2", "host b"]):
        return "Host 2"

    return "Host 1" if "host" in s else raw_speaker.strip()


class DialogueParser:
    """
    6-Tier Resilient Dialogue Parser.
    Guarantees parsing of LLM outputs across various formatting quirks.
    """

    @classmethod
    def parse(cls, raw_output: str, default_language: str = "en-US") -> List[DialogueTurn]:
        """
        Parses raw LLM string into List[DialogueTurn] using 6 cascading recovery tiers.
        
        Tiers:
        - Tier 1: Direct JSON parse
        - Tier 2: Markdown code fence block extraction (```json ... ```)
        - Tier 3: Substring outer bracket trimmer ([ ... ])
        - Tier 4: Syntax sanitizer (trailing commas, single quotes, control chars)
        - Tier 5: Line-by-line / object-by-object regex extractor
        - Tier 6: Plain-text transcript line salvager
        
        Raises:
            ValueError: If parsing fails across all 6 tiers or returns empty dialogue.
        """
        if not raw_output or not isinstance(raw_output, str) or not raw_output.strip():
            raise ValueError("LLM returned empty or non-string dialogue output.")

        cleaned = raw_output.strip()

        # ======================================================================
        # Tier 1: Direct JSON parsing
        # ======================================================================
        try:
            data = json.loads(cleaned)
            turns = cls._validate_and_convert(data)
            if turns:
                return turns
        except Exception:
            pass

        # ======================================================================
        # Tier 2: Markdown Code Fence Extraction (```json ... ``` or ``` ... ```)
        # ======================================================================
        fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        for fence_content in fence_matches:
            fence_content = fence_content.strip()
            try:
                data = json.loads(fence_content)
                turns = cls._validate_and_convert(data)
                if turns:
                    return turns
            except Exception:
                # Try bracket trimming on fence content
                sub_turns = cls._try_bracket_parse(fence_content)
                if sub_turns:
                    return sub_turns

        # ======================================================================
        # Tier 3: Substring Outer Bracket Trimming
        # ======================================================================
        turns = cls._try_bracket_parse(cleaned)
        if turns:
            return turns

        # ======================================================================
        # Tier 4: Syntax Normalization & Sanitization
        # ======================================================================
        sanitized = cls._sanitize_json_string(cleaned)
        turns = cls._try_bracket_parse(sanitized)
        if turns:
            return turns

        try:
            data = json.loads(sanitized)
            turns = cls._validate_and_convert(data)
            if turns:
                return turns
        except Exception:
            pass

        # ======================================================================
        # Tier 5: Object-by-Object Regex Extractor
        # ======================================================================
        turns = cls._regex_object_parser(cleaned)
        if turns:
            return turns

        # ======================================================================
        # Tier 6: Plain-Text Transcript Line Salvager
        # ======================================================================
        turns = cls._transcript_salvage_parser(cleaned)
        if turns:
            return turns

        raise ValueError("Failed to parse dialogue script from LLM output across all 6 parser tiers.")

    @classmethod
    def _try_bracket_parse(cls, text: str) -> Optional[List[DialogueTurn]]:
        """Finds outer [ ... ] brackets and attempts JSON parsing."""
        start_idx = text.find("[")
        end_idx = text.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            bracket_slice = text[start_idx:end_idx + 1].strip()
            try:
                data = json.loads(bracket_slice)
                return cls._validate_and_convert(data)
            except Exception:
                # Try sanitizing bracket slice
                sanitized = cls._sanitize_json_string(bracket_slice)
                try:
                    data = json.loads(sanitized)
                    return cls._validate_and_convert(data)
                except Exception:
                    pass
        return None

    @classmethod
    def _sanitize_json_string(cls, text: str) -> str:
        """Fixes common LLM JSON syntax errors."""
        # Replace smart/curly quotes with standard double/single quotes
        s = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

        # Strip trailing commas before closing brackets or braces
        s = re.sub(r",\s*([\]}])", r"\1", s)

        # Fix single-quoted keys and values
        # e.g. {'speaker': 'Host 1', 'text': 'Hello'}
        s = re.sub(r"'(speaker|host|name|role|text|content|dialogue|line)'\s*:", r'"\1":', s)
        s = re.sub(r":\s*'([^']*)'", r': "\1"', s)

        # Clean unescaped ASCII control characters in strings
        s = re.sub(
            r"[\x00-\x1f]",
            lambda m: "\\u{:04x}".format(ord(m.group(0))) if m.group(0) not in "\r\n\t" else m.group(0),
            s
        )

        return s

    @classmethod
    def _validate_and_convert(cls, data: Any) -> Optional[List[DialogueTurn]]:
        """Converts raw parsed data into List[DialogueTurn]."""
        if isinstance(data, dict):
            # Handle {"dialogue": [...]} or {"turns": [...]} or {"podcast": [...]}
            for key in ["dialogue", "turns", "script", "podcast", "conversation", "episode"]:
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                # Dict of single turn
                if "speaker" in data and ("text" in data or "content" in data):
                    data = [data]
                else:
                    return None

        if not isinstance(data, list):
            return None

        turns: List[DialogueTurn] = []
        for item in data:
            if isinstance(item, dict):
                turn = DialogueTurn.from_dict(item)
                if turn.text:
                    turns.append(turn)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                spk = normalize_speaker(str(item[0]))
                txt = str(item[1]).strip()
                if txt:
                    turns.append(DialogueTurn(speaker=spk, text=txt))

        return turns if turns else None

    @classmethod
    def _regex_object_parser(cls, text: str) -> Optional[List[DialogueTurn]]:
        """Extracts individual dialogue turn objects using regex."""
        pattern1 = re.compile(
            r'\{\s*["\']?(?:speaker|host|name|role)["\']?\s*:\s*["\'](?P<speaker>[^"\']+)["\']\s*,\s*["\']?(?:text|content|dialogue|line)["\']?\s*:\s*["\'](?P<text>(?:\\.|[^"\\])*?)["\']\s*\}',
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        pattern2 = re.compile(
            r'\{\s*["\']?(?:text|content|dialogue|line)["\']?\s*:\s*["\'](?P<text>(?:\\.|[^"\\])*?)["\']\s*,\s*["\']?(?:speaker|host|name|role)["\']?\s*:\s*["\'](?P<speaker>[^"\']+)["\']\s*\}',
            re.MULTILINE | re.DOTALL | re.IGNORECASE
        )

        matches = list(pattern1.finditer(text))
        if not matches:
            matches = list(pattern2.finditer(text))

        turns: List[DialogueTurn] = []
        for match in matches:
            spk = normalize_speaker(match.group("speaker"))
            raw_txt = match.group("text")
            try:
                txt = raw_txt.encode("utf-8").decode("unicode_escape", errors="ignore")
                txt = txt.replace('\\"', '"').replace("\\'", "'")
            except Exception:
                txt = raw_txt
            txt = txt.strip()
            if txt:
                turns.append(DialogueTurn(speaker=spk, text=txt))

        return turns if turns else None

    @classmethod
    def _transcript_salvage_parser(cls, text: str) -> Optional[List[DialogueTurn]]:
        """
        Parses line-by-line plain-text transcript formats:
        e.g. 'Host 1: Hello everyone!', '**Kari:** Hei!', '- Guy: Great point.'
        Supports multi-line turn continuations.
        """
        line_pattern = re.compile(
            r"^(?:[\*\-\#\_\[\s]*)(Host\s*[12]|Kari|Ola|Jenny|Guy|Speaker\s*[12])(?:[\*\_\]\s]*)\s*:\s*(?:\*{0,2})\s*(.+)$",
            re.IGNORECASE
        )

        turns: List[DialogueTurn] = []
        current_speaker: Optional[str] = None
        current_lines: List[str] = []

        def flush_current():
            nonlocal current_speaker, current_lines
            if current_speaker and current_lines:
                full_text = " ".join(current_lines).strip()
                if full_text:
                    turns.append(DialogueTurn(speaker=current_speaker, text=full_text))
            current_speaker = None
            current_lines = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = line_pattern.match(line)
            if match:
                flush_current()
                current_speaker = normalize_speaker(match.group(1))
                line_content = match.group(2).strip()
                line_content = re.sub(r"^\*{1,2}|\*{1,2}$", "", line_content).strip()
                if line_content:
                    current_lines.append(line_content)
            elif current_speaker is not None:
                if not line.startswith("```") and not line.startswith("---") and not line.startswith("#"):
                    current_lines.append(line)

        flush_current()
        return turns if turns else None


# Convenience alias functions
parse_dialogue_json = DialogueParser.parse


def dialogue_to_json(turns: List[DialogueTurn], indent: int = 2) -> str:
    """Serializes a list of dialogue turns to a formatted JSON string."""
    data = [turn.to_dict() for turn in turns]
    return json.dumps(data, indent=indent, ensure_ascii=False)


def dialogue_from_json(json_str: str) -> List[DialogueTurn]:
    """Deserializes a JSON string into a list of dialogue turns using DialogueParser."""
    return DialogueParser.parse(json_str)


def dialogue_to_markdown(turns: List[DialogueTurn], language: str = "nb-NO") -> str:
    """Formats dialogue turns into readable Markdown transcript."""
    lines = ["# Podcast Transcript\n"]
    for idx, turn in enumerate(turns, start=1):
        if turn.speaker == "Host 1":
            speaker_label = "Host 1 (Kari)" if "nb" in language.lower() else "Host 1 (Jenny)"
        else:
            speaker_label = "Host 2 (Ola)" if "nb" in language.lower() else "Host 2 (Guy)"
        lines.append(f"**{speaker_label}**: {turn.text}\n")
    return "\n".join(lines)
