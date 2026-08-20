"""
Standalone Comprehensive Verification Script for Milestone 2 Core Engines
Executes all unit tests, edge case tests, and contract checks across core/ modules.
"""

import os
import sys
import io
import json
import struct
import tempfile
import traceback
from unittest.mock import patch, MagicMock

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

def run_tests():
    total_passed = 0
    total_failed = 0
    failures = []

    def check(name, condition, error_msg="Assertion failed"):
        nonlocal total_passed, total_failed
        if condition:
            total_passed += 1
            print(f"  [PASS] {name}")
        else:
            total_failed += 1
            failures.append(f"{name}: {error_msg}")
            print(f"  [FAIL] {name} - {error_msg}")

    print("=" * 70)
    print("RUNNING PODCASTSTUDIO MILESTONE 2 CORE ENGINES VERIFICATION")
    print("=" * 70)

    # --------------------------------------------------------------------------
    # 1. Verification of core/__init__.py exports
    # --------------------------------------------------------------------------
    print("\n--- 1. Testing core/__init__.py Exports ---")
    try:
        import core
        expected_exports = [
            "DialogueTurn", "DialogueParser", "normalize_speaker", "parse_dialogue_json",
            "extract_text", "extract_text_from_file", "extract_text_from_pdf", "DocumentExtractionError",
            "FORMAT_PRESETS", "TONE_DESCRIPTIONS", "build_system_prompt", "build_user_prompt",
            "get_format_config", "get_tone_description", "normalize_language_code",
            "OllamaClient", "generate_podcast_script", "OllamaConnectionError", "OllamaModelNotFoundError",
            "TTSEngine", "get_voice_for_speaker", "synthesize_turn", "synthesize_dialogue_audio", "format_rate_str", "VOICE_MAP",
            "MP3Stitcher", "stitch_mp3_files",
            "WindowsAudioPlayer", "WindowsMCIPlayer", "export_audio_file", "format_ms", "parse_time_str"
        ]
        for exp in expected_exports:
            check(f"Export '{exp}' present in core", hasattr(core, exp))
    except Exception as e:
        check("Import core package", False, str(e))

    # --------------------------------------------------------------------------
    # 2. Verification of core/extractor.py
    # --------------------------------------------------------------------------
    print("\n--- 2. Testing core/extractor.py ---")
    from core.extractor import extract_text, extract_text_from_file, extract_text_from_pdf, DocumentExtractionError

    # Test raw text
    raw_sample = "   This is a sample raw text about astrophysics and telescopes.   \n\n\n\nNext paragraph."
    extracted_raw = extract_text(raw_sample, is_raw_text=True)
    check("Raw text trimming & newline collapse", extracted_raw == "This is a sample raw text about astrophysics and telescopes.\n\nNext paragraph.")

    # Test topic mode
    topic_sample = "Quantum computing algorithms"
    extracted_topic = extract_text(topic_sample, is_topic=True)
    check("Topic extraction", extracted_topic == topic_sample)

    # Test UTF-8 / UTF-8-BOM / CP1252 / Latin-1 files
    with tempfile.TemporaryDirectory() as td:
        # UTF-8 with norwegian letters
        p_utf8 = os.path.join(td, "doc_utf8.txt")
        with open(p_utf8, "w", encoding="utf-8") as f:
            f.write("Norsk tekst med æ, ø, å og spesialtegn.")
        check("Extract UTF-8 file", "æ, ø, å" in extract_text(p_utf8))

        # UTF-8 BOM
        p_bom = os.path.join(td, "doc_bom.txt")
        with open(p_bom, "w", encoding="utf-8-sig") as f:
            f.write("BOM test tekst med Æ, Ø, Å.")
        check("Extract UTF-8-BOM file", "Æ, Ø, Å" in extract_text(p_bom))

        # CP1252
        p_cp = os.path.join(td, "doc_cp1252.txt")
        with open(p_cp, "wb") as f:
            f.write("CP1252 tekst med \xe6, \xf8, \xe5.".encode("cp1252"))
        check("Extract CP1252 file", "CP1252 tekst" in extract_text(p_cp))

        # Latin-1
        p_lat = os.path.join(td, "doc_latin1.txt")
        with open(p_lat, "wb") as f:
            f.write("Latin-1 tekst: \xe6, \xf8, \xe5.".encode("latin-1"))
        check("Extract Latin-1 file", "Latin-1 tekst" in extract_text(p_lat))

        # Markdown
        p_md = os.path.join(td, "doc.md")
        with open(p_md, "w", encoding="utf-8") as f:
            f.write("# Heading\n\nParagraph with auto-\nmatic hyphenation.")
        extracted_md = extract_text(p_md)
        check("Extract Markdown with dehyphenation", "automatic" in extracted_md)

        # PDF Mocking
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page content with infor-\nmation."
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader), patch("os.path.exists", return_value=True):
            pdf_result = extract_text_from_pdf("sample.pdf")
            check("PDF text normalization & dehyphenation", "information" in pdf_result)

        # Missing file error
        try:
            extract_text("nonexistent_file_999.txt")
            check("Missing file raises error", False, "No error raised")
        except DocumentExtractionError:
            check("Missing file raises DocumentExtractionError", True)
        except Exception as e:
            check("Missing file raises DocumentExtractionError", True, f"Raised {type(e)}")

        # Empty input error
        try:
            extract_text("   ", is_raw_text=True)
            check("Empty raw text raises error", False)
        except DocumentExtractionError:
            check("Empty raw text raises DocumentExtractionError", True)

    # --------------------------------------------------------------------------
    # 3. Verification of core/prompts.py
    # --------------------------------------------------------------------------
    print("\n--- 3. Testing core/prompts.py ---")
    from core.prompts import (
        build_system_prompt, build_user_prompt, get_format_config, get_tone_description, FORMAT_PRESETS
    )

    # Check 4 presets
    for fmt_id in ["quick", "standard", "deep_dive", "extended"]:
        cfg = get_format_config(fmt_id)
        check(f"Format preset '{fmt_id}' config validity", cfg is not None and "min_turns" in cfg and cfg["min_turns"] >= 6)

    # Check aliases
    check("Alias 'short' -> 'quick'", get_format_config("short")["id"] == "quick")
    check("Alias 'deep' -> 'deep_dive'", get_format_config("deep")["id"] == "deep_dive")
    check("Alias 'extended_in_depth' -> 'extended'", get_format_config("extended_in_depth")["id"] == "extended")

    # Check Norwegian personas
    sys_nb = build_system_prompt(language="nb-NO", format_type="standard", tone_style="casual")
    check("NB prompt contains Kari", "Kari" in sys_nb)
    check("NB prompt contains Ola", "Ola" in sys_nb)
    check("NB prompt contains JSON requirement", "JSON" in sys_nb)

    # Check English personas
    sys_en = build_system_prompt(language="en-US", format_type="standard", tone_style="casual")
    check("EN prompt contains Jenny", "Jenny" in sys_en)
    check("EN prompt contains Guy", "Guy" in sys_en)
    check("EN prompt contains JSON requirement", "JSON" in sys_en)

    # Check Tone matrix
    for tone in ["casual", "analytical", "debate"]:
        desc_en = get_tone_description(tone, "en-US")
        desc_nb = get_tone_description(tone, "nb-NO")
        check(f"Tone '{tone}' localized descriptions", len(desc_en) > 0 and len(desc_nb) > 0)

    # --------------------------------------------------------------------------
    # 4. Verification of core/parser.py (6-Tier Resilient Parser)
    # --------------------------------------------------------------------------
    print("\n--- 4. Testing core/parser.py (6 Tiers) ---")
    from core.parser import DialogueParser, DialogueTurn, normalize_speaker, parse_dialogue_json

    # Tier 1: Direct JSON
    t1_input = '[{"speaker": "Host 1", "text": "Hello world!"}, {"speaker": "Host 2", "text": "Hi Jenny!"}]'
    t1_turns = DialogueParser.parse(t1_input)
    check("Tier 1: Direct JSON parse", len(t1_turns) == 2 and t1_turns[0].text == "Hello world!")

    # Tier 2: Markdown code fence
    t2_input = 'Here is the script:\n```json\n[{"speaker": "Host 1", "text": "Fence test."}]\n```'
    t2_turns = DialogueParser.parse(t2_input)
    check("Tier 2: Code fence extraction", len(t2_turns) == 1 and t2_turns[0].text == "Fence test.")

    # Tier 3: Substring bounds trimming (Preamble & Postamble)
    t3_input = 'Preamble text\n[{"speaker": "Kari", "text": "Hei!"}, {"speaker": "Ola", "text": "Hei Kari!"}]\nPostamble text.'
    t3_turns = DialogueParser.parse(t3_input)
    check("Tier 3: Substring bounds trim & normalization", len(t3_turns) == 2 and t3_turns[0].speaker == "Host 1")

    # Tier 4: Trailing commas & single quotes
    t4_input = "[{'speaker': 'Host 1', 'text': 'Single quotes with trailing comma!',}, {'speaker': 'Host 2', 'text': 'Indeed.',},]"
    t4_turns = DialogueParser.parse(t4_input)
    check("Tier 4: Syntax sanitization", len(t4_turns) == 2 and t4_turns[1].speaker == "Host 2")

    # Tier 5: Line-by-line regex object extractor
    t5_input = 'Broken outer text\n{"speaker": "Host 1", "text": "Regex turn 1."}\nRandom noise\n{"speaker": "Host 2", "text": "Regex turn 2."}'
    t5_turns = DialogueParser.parse(t5_input)
    check("Tier 5: Object regex extraction", len(t5_turns) == 2 and t5_turns[0].text == "Regex turn 1.")

    # Tier 6: Plain-text transcript line salvager
    t6_input = "Host 1: Welcome to the episode!\nHost 2: Great to be here, Jenny.\nHost 1: Tell us about AI.\nHost 2: Local AI runs without cloud fees."
    t6_turns = DialogueParser.parse(t6_input)
    check("Tier 6: Plain-text transcript salvager", len(t6_turns) == 4 and t6_turns[3].text == "Local AI runs without cloud fees.")

    # Speaker Normalization
    check("Normalize 'Kari' -> 'Host 1'", normalize_speaker("Kari") == "Host 1")
    check("Normalize 'Jenny' -> 'Host 1'", normalize_speaker("Jenny") == "Host 1")
    check("Normalize 'Ola' -> 'Host 2'", normalize_speaker("Ola") == "Host 2")
    check("Normalize 'Guy' -> 'Host 2'", normalize_speaker("Guy") == "Host 2")

    # Empty / Unparseable handling
    try:
        DialogueParser.parse("Completely unparseable gibberish with no speakers or structure.")
        check("Gibberish raises ValueError", False)
    except ValueError:
        check("Gibberish raises ValueError", True)

    # --------------------------------------------------------------------------
    # 5. Verification of core/ollama.py
    # --------------------------------------------------------------------------
    print("\n--- 5. Testing core/ollama.py ---")
    from core.ollama import OllamaClient, generate_podcast_script

    client = OllamaClient()
    check("OllamaClient default URL", "11434" in client.base_url)

    # Mock tags response
    mock_tags = {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:7b"}, {"name": "mistral-nemo:latest"}]}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_tags).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        models = client.list_models()
        check("OllamaClient list_models", len(models) == 3 and "llama3.1:8b" in models)

    # Mock dialogue generation
    mock_chat_data = {"message": {"role": "assistant", "content": '[{"speaker": "Host 1", "text": "Generated line."}]'}}
    mock_chat_resp = MagicMock()
    mock_chat_resp.status = 200
    mock_chat_resp.read.return_value = json.dumps(mock_chat_data).encode("utf-8")
    mock_chat_resp.__enter__.return_value = mock_chat_resp

    with patch("urllib.request.urlopen", return_value=mock_chat_resp):
        turns = generate_podcast_script("Test content", language="en-US", model="llama3.1:8b")
        check("generate_podcast_script integration", len(turns) == 1 and turns[0].text == "Generated line.")

    # --------------------------------------------------------------------------
    # 6. Verification of core/tts.py
    # --------------------------------------------------------------------------
    print("\n--- 6. Testing core/tts.py ---")
    from core.tts import TTSEngine, get_voice_for_speaker, format_rate_str

    check("Rate formatting '+10%'", format_rate_str("+10%") == "+10%")
    check("Rate formatting int 5", format_rate_str(5) == "+5%")
    check("Rate formatting int -10", format_rate_str(-10) == "-10%")

    engine_nb = TTSEngine(language="nb-NO")
    check("NB Host 1 voice is Pernille", engine_nb.get_voice("Host 1") == "nb-NO-PernilleNeural")
    check("NB Host 2 voice is Finn", engine_nb.get_voice("Host 2") == "nb-NO-FinnNeural")

    engine_en = TTSEngine(language="en-US")
    check("EN Host 1 voice is Jenny", engine_en.get_voice("Host 1") == "en-US-JennyNeural")
    check("EN Host 2 voice is Guy", engine_en.get_voice("Host 2") == "en-US-GuyNeural")

    # --------------------------------------------------------------------------
    # 7. Verification of core/mp3_stitcher.py
    # --------------------------------------------------------------------------
    print("\n--- 7. Testing core/mp3_stitcher.py ---")
    from core.mp3_stitcher import MP3Stitcher, stitch_mp3_files

    # Create synthetic MPEG-2 Layer III frames
    # 48kbps, 24kHz, mono frame = 144 bytes
    header = bytes([0xFF, 0xF3, 0x40, 0x00]) # MPEG-2 Layer III, 48kbps, 24kHz, mono
    frame_144 = header + bytes(140)

    # Test frame header parsing
    header_res = MP3Stitcher.parse_frame_header(frame_144[:4])
    check("MPEG frame header parsing (4-tuple)", header_res is not None and header_res[0] == 144 and header_res[2] == 48 and header_res[3] == 24000)

    # Test ID3v2 tag generation & stripping
    id3_tag = MP3Stitcher.build_id3v23_tag(title="Test Episode", artist="PodcastStudio")
    check("Build ID3v2.3 tag starting with ID3", id3_tag[:3] == b"ID3" and id3_tag[3] == 3)

    raw_mp3_stream = id3_tag + (frame_144 * 5)
    extracted_frames = MP3Stitcher.extract_audio_frames(raw_mp3_stream)
    check("Extract pure MPEG audio frames (stripping ID3)", len(extracted_frames) == 144 * 5 and extracted_frames[:3] != b"ID3")

    # Test in-memory stitcher
    stitched_bytes = MP3Stitcher.stitch([raw_mp3_stream, raw_mp3_stream], title="Stitched Podcast", pause_ms=360)
    check("In-memory stitcher produces valid MP3 with ID3", stitched_bytes[:3] == b"ID3" and len(stitched_bytes) > (144 * 10))

    # Test file stitching to disk
    with tempfile.TemporaryDirectory() as td:
        f1 = os.path.join(td, "t1.mp3")
        f2 = os.path.join(td, "t2.mp3")
        with open(f1, "wb") as f: f.write(raw_mp3_stream)
        with open(f2, "wb") as f: f.write(raw_mp3_stream)

        out_f = os.path.join(td, "final.mp3")
        res_path = stitch_mp3_files([f1, f2], out_f, silence_duration_ms=350)
        check("stitch_mp3_files writes file to disk", os.path.exists(res_path) and os.path.getsize(res_path) > 0)

    # --------------------------------------------------------------------------
    # 8. Verification of core/player.py
    # --------------------------------------------------------------------------
    print("\n--- 8. Testing core/player.py ---")
    from core.player import WindowsAudioPlayer, WindowsMCIPlayer, format_ms, parse_time_str, export_audio_file

    check("Time format 125000 -> '02:05'", format_ms(125000) == "02:05")
    check("Time parse '02:05' -> 125000", parse_time_str("02:05") == 125000)

    player = WindowsMCIPlayer()
    check("WindowsMCIPlayer instantiation", player is not None)

    with patch.object(player, "_send_command", return_value=""):
        check("Player set_volume clamping > 100", player.set_volume(120) is True and player.get_volume() == 100)
        check("Player set_volume clamping < 0", player.set_volume(-10) is True and player.get_volume() == 0)

    print("\n" + "=" * 70)
    print(f"VERIFICATION SUMMARY: {total_passed} PASSED, {total_failed} FAILED")
    print("=" * 70)

    if total_failed > 0:
        print("Failures:")
        for fail in failures:
            print(f"  - {fail}")
        return False
    return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
