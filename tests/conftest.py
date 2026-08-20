"""
PodcastStudio Test Suite - Shared Fixtures and Utilities
=========================================================
Provides reusable test fixtures, mock servers, synthetic MPEG audio generators,
sample document factories, and simulated external services (Ollama, Edge-TTS, WinMM).
"""

import os
import io
import struct
import tempfile
import pytest
from typing import List, Dict, Any, Generator

# Import core models if available or provide fallback
try:
    from core.parser import DialogueTurn
except ImportError:
    try:
        from core.models import DialogueTurn
    except ImportError:
        from dataclasses import dataclass
        @dataclass
        class DialogueTurn:
            speaker: str
            text: str


# ==============================================================================
# Synthetic MPEG Frame & MP3 Generators
# ==============================================================================

def make_mpeg2_l3_frame(bitrate_idx: int = 4, sr_idx: int = 1, padding: int = 0) -> bytes:
    """
    Creates a valid MPEG-2 Layer III 24kHz / 48kbps audio frame.
    Header format:
      b0: 0xFF
      b1: 0xF3 (MPEG-2, Layer III, No CRC = 1111 0011)
      b2: (bitrate_idx << 4) | (sr_idx << 2) | (padding << 1)
      b3: 0x00 (Single channel / mono)
    FrameLength = int((72 * bitrate * 1000) / sample_rate) + padding
    For 48kbps (bitrate_idx=4) and 24kHz (sr_idx=1): 72 * 48000 / 24000 = 144 bytes.
    """
    b0 = 0xFF
    b1 = 0xF3  # MPEG-2, Layer III, No CRC
    b2 = ((bitrate_idx & 0x0F) << 4) | ((sr_idx & 0x03) << 2) | ((padding & 0x01) << 1)
    b3 = 0x00  # Mono mode

    header = bytes([b0, b1, b2, b3])
    # Bitrate in kbps for MPEG-2 L3: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    bitrates = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    sr_rates = [22050, 24000, 16000]
    bitrate = bitrates[bitrate_idx]
    sample_rate = sr_rates[sr_idx]
    frame_len = int((72 * bitrate * 1000) / sample_rate) + padding
    payload_len = max(0, frame_len - 4)
    payload = b"\x55" * payload_len  # Non-zero audio dummy payload
    return header + payload


def make_id3v2_tag(title: str = "Test Title", artist: str = "Test Artist") -> bytes:
    """
    Creates an authentic ID3v2.3 tag with synchsafe integer size calculation.
    """
    frames = io.BytesIO()

    for frame_id, val in [("TIT2", title), ("TPE1", artist)]:
        data = b"\x00" + val.encode("latin-1", errors="replace")
        frames.write(frame_id.encode("ascii"))
        frames.write(struct.pack(">I", len(data)))
        frames.write(b"\x00\x00")  # Flags
        frames.write(data)

    frames_data = frames.getvalue()
    tag_size = len(frames_data)

    # Convert tag_size to 28-bit synchsafe integer
    b0 = (tag_size >> 21) & 0x7F
    b1 = (tag_size >> 14) & 0x7F
    b2 = (tag_size >> 7) & 0x7F
    b3 = tag_size & 0x7F

    header = b"ID3\x03\x00\x00" + bytes([b0, b1, b2, b3])
    return header + frames_data


def make_id3v1_tag(title: str = "Test Title", artist: str = "Test Artist") -> bytes:
    """Creates a standard 128-byte ID3v1 trailing tag."""
    tag = bytearray(128)
    tag[:3] = b"TAG"
    t_bytes = title.encode("ascii", errors="replace")[:30]
    a_bytes = artist.encode("ascii", errors="replace")[:30]
    tag[3:3+len(t_bytes)] = t_bytes
    tag[33:33+len(a_bytes)] = a_bytes
    return bytes(tag)


def make_synthetic_mp3(
    num_frames: int = 10,
    include_id3v2: bool = True,
    include_id3v1: bool = False,
    title: str = "Turn Audio",
    artist: str = "PodcastStudio"
) -> bytes:
    """Builds a complete synthetic MP3 binary with headers, frames, and optional tags."""
    out = io.BytesIO()
    if include_id3v2:
        out.write(make_id3v2_tag(title=title, artist=artist))
    for _ in range(num_frames):
        out.write(make_mpeg2_l3_frame(bitrate_idx=4, sr_idx=1))
    if include_id3v1:
        out.write(make_id3v1_tag(title=title, artist=artist))
    return out.getvalue()


@pytest.fixture
def synthetic_mp3_factory():
    """Fixture providing factory for generating test MP3 byte buffers."""
    return make_synthetic_mp3


@pytest.fixture
def single_frame_mp3() -> bytes:
    """Returns a single valid MPEG-2 Layer III frame."""
    return make_mpeg2_l3_frame()


@pytest.fixture
def multi_frame_mp3() -> bytes:
    """Returns an MP3 containing ID3v2 header and 5 audio frames."""
    return make_synthetic_mp3(num_frames=5, include_id3v2=True)


# ==============================================================================
# Document & File Fixtures
# ==============================================================================

@pytest.fixture
def sample_text_utf8(tmp_path) -> str:
    """Generates a sample UTF-8 encoded text document."""
    content = (
        "PodcastStudio Test Document\n"
        "Dette er et testdokument på norsk med spesialtegn: æ, ø, å.\n"
        "PodcastStudio gjør det enkelt å lage to-stemmers podcasts med lokal KI.\n"
        "Vert 1 stiller spørsmål, mens Vert 2 forklarer faglige temaer i dybden."
    )
    p = tmp_path / "sample_utf8.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def sample_text_utf8_bom(tmp_path) -> str:
    """Generates a sample UTF-8 with BOM text document."""
    content = (
        "PodcastStudio BOM Document\n"
        "Tekst med UTF-8 Byte Order Mark (BOM).\n"
        "Inneholder norske bokstaver: Æ, Ø, Å."
    )
    p = tmp_path / "sample_utf8_bom.txt"
    p.write_text(content, encoding="utf-8-sig")
    return str(p)


@pytest.fixture
def sample_text_cp1252(tmp_path) -> str:
    """Generates a sample Windows CP1252 encoded text document."""
    content = (
        "PodcastStudio CP1252 Document\n"
        "Windows-1252 encoded document with characters: \u00e6, \u00f8, \u00e5."
    )
    p = tmp_path / "sample_cp1252.txt"
    p.write_bytes(content.encode("cp1252"))
    return str(p)


@pytest.fixture
def sample_text_latin1(tmp_path) -> str:
    """Generates a sample ISO-8859-1 (Latin-1) encoded text document."""
    content = (
        "PodcastStudio Latin-1 Document\n"
        "ISO-8859-1 encoded content: \u00e6, \u00f8, \u00e5, \u00e9, \u00fc."
    )
    p = tmp_path / "sample_latin1.txt"
    p.write_bytes(content.encode("latin-1"))
    return str(p)


@pytest.fixture
def sample_markdown_file(tmp_path) -> str:
    """Generates a sample Markdown document."""
    content = (
        "# Kunstig Intelligens i Hverdagen\n\n"
        "## Introduksjon\n"
        "Hvordan påvirker maskinlæring og store språkmodeller hverdagen vår i dag?\n\n"
        "### Hovedpunkter\n"
        "- **Lokale modeller**: Kjører 100% lokalt på din egen PC via Ollama.\n"
        "- **Tale-syntese**: Edge-TTS gir naturlige norske stemmer som Pernille og Finn.\n"
        "- **Personvern**: Ingen data sendes til skyen eller tredjeparter.\n\n"
        "## Konklusjon\n"
        "Dette representerer et paradigmeskifte for tilgjengelig podcast-produksjon."
    )
    p = tmp_path / "sample_document.md"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture
def sample_pdf_file(tmp_path) -> str:
    """Generates a valid test PDF file containing extractable text using pypdf/io."""
    try:
        from pypdf import PdfWriter
        writer = PdfWriter()
        # Add an empty page with some mock text if possible, or build basic PDF stream
        # Minimal valid PDF structure with text stream
        p = tmp_path / "sample_document.pdf"
        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            b"4 0 obj << /Length 55 >> stream\n"
            b"BT /F1 12 Tf 72 712 Td (PodcastStudio PDF Ingestion Test Document) Tj ET\n"
            b"endstream\n"
            b"endobj\n"
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"xref\n"
            b"0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000244 00000 n \n"
            b"0000000350 00000 n \n"
            b"trailer << /Size 6 /Root 1 0 R >>\n"
            b"startxref\n"
            b"424\n"
            b"%%EOF\n"
        )
        p.write_bytes(pdf_content)
        return str(p)
    except Exception:
        p = tmp_path / "sample_document.pdf"
        p.write_bytes(b"%PDF-1.4 mock pdf data")
        return str(p)


@pytest.fixture
def sample_corrupted_pdf(tmp_path) -> str:
    """Generates a corrupted, unreadable PDF file."""
    p = tmp_path / "corrupt.pdf"
    p.write_bytes(b"NOT A REAL PDF FILE HEADER 1234567890")
    return str(p)


# ==============================================================================
# Dialogue & LLM Output Fixtures
# ==============================================================================

@pytest.fixture
def sample_norwegian_turns() -> List[DialogueTurn]:
    """Sample list of DialogueTurn dataclasses in Norwegian."""
    return [
        DialogueTurn(speaker="Host 1", text="Hei og hjertelig velkommen til dagens episode av PodcastStudio!"),
        DialogueTurn(speaker="Host 2", text="Hei Kari! I dag skal vi ta for oss et utrolig spennende tema."),
        DialogueTurn(speaker="Host 1", text="Ja, vi skal snakke om hvordan store språkmodeller fungerer lokalt."),
        DialogueTurn(speaker="Host 2", text="Det stemmer. Med verktøy som Ollama kan hvem som helst kjøre avansert KI rett på egen maskin."),
        DialogueTurn(speaker="Host 1", text="Tusen takk for en fantastisk samtale, Ola, og takk til alle som lyttet på!"),
        DialogueTurn(speaker="Host 2", text="Takk for i dag, Kari! Vi høres igjen i neste episode.")
    ]


@pytest.fixture
def sample_english_turns() -> List[DialogueTurn]:
    """Sample list of DialogueTurn dataclasses in English."""
    return [
        DialogueTurn(speaker="Host 1", text="Welcome back to the show, everyone! Today we have an exciting topic."),
        DialogueTurn(speaker="Host 2", text="Great to be here, Jenny! We're diving into local AI and offline audio synthesis."),
        DialogueTurn(speaker="Host 1", text="How does PodcastStudio manage to generate studio audio without cloud fees?"),
        DialogueTurn(speaker="Host 2", text="It pairs local LLMs via Ollama with Edge-TTS and direct binary MP3 stitching."),
        DialogueTurn(speaker="Host 1", text="That is truly remarkable. Thanks for tuning in everyone!"),
        DialogueTurn(speaker="Host 2", text="Thanks Jenny, and see you all next time!")
    ]


@pytest.fixture
def llm_output_cases() -> Dict[str, str]:
    """Provides a variety of LLM output formats to test parser resilience."""
    return {
        "pure_json": (
            '[\n'
            '  {"speaker": "Host 1", "text": "Welcome to the show!"},\n'
            '  {"speaker": "Host 2", "text": "Glad to be here, Jenny!"}\n'
            ']'
        ),
        "markdown_fenced": (
            'Here is your podcast script:\n\n'
            '```json\n'
            '[\n'
            '  {"speaker": "Host 1", "text": "Welcome to the show!"},\n'
            '  {"speaker": "Host 2", "text": "Glad to be here, Jenny!"}\n'
            ']\n'
            '```\n\n'
            'I hope this meets your expectations!'
        ),
        "fenced_no_lang": (
            '```\n'
            '[\n'
            '  {"speaker": "Host 1", "text": "Welcome to the show!"},\n'
            '  {"speaker": "Host 2", "text": "Glad to be here, Jenny!"}\n'
            ']\n'
            '```'
        ),
        "trailing_commas": (
            '[\n'
            '  {"speaker": "Host 1", "text": "Welcome to the show!",},\n'
            '  {"speaker": "Host 2", "text": "Glad to be here, Jenny!",}\n'
            ']'
        ),
        "single_quotes": (
            "[\n"
            "  {'speaker': 'Host 1', 'text': 'Welcome to the show!'},\n"
            "  {'speaker': 'Host 2', 'text': 'Glad to be here, Jenny!'}\n"
            "]"
        ),
        "preamble_and_postamble": (
            "Sure thing! Here is the dialogue between Kari and Ola:\n"
            '[\n'
            '  {"speaker": "Kari", "text": "Hei og velkommen!"},\n'
            '  {"speaker": "Ola", "text": "Hei Kari, spennende tema i dag!"}\n'
            ']\n'
            "Let me know if you need any adjustments!"
        ),
        "broken_brackets_regex": (
            'Some broken intro without valid outer array:\n'
            '{"speaker": "Host 1", "text": "First line of dialogue."}\n'
            '{"speaker": "Host 2", "text": "Second line answering the question."}\n'
            'End of generation.'
        ),
        "plain_text_transcript": (
            "Host 1: Welcome to the episode everyone!\n"
            "Host 2: Hi Jenny, great to discuss this document today.\n"
            "Host 1: Can you give us an executive overview?\n"
            "Host 2: Absolutely, the core takeaway is rapid automation."
        ),
        "norwegian_plain_transcript": (
            "Kari: Hei og velkommen til podcasten!\n"
            "Ola: Hei Kari! I dag skal vi se nærmere på rapporten.\n"
            "Kari: Hva er de viktigste funnene?\n"
            "Ola: Hovedfunnet er en markant økning i produktivitet."
        )
    }


# ==============================================================================
# Mock Ollama API Fixtures
# ==============================================================================

@pytest.fixture
def mock_ollama_tags_data() -> Dict[str, Any]:
    """Standard mock data returned by GET /api/tags."""
    return {
        "models": [
            {
                "name": "llama3.1:8b",
                "model": "llama3.1:8b",
                "size": 4920754890,
                "modified_at": "2026-08-20T12:00:00Z",
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "parameter_size": "8.0B",
                    "quantization_level": "Q4_K_M"
                }
            },
            {
                "name": "qwen2.5:7b",
                "model": "qwen2.5:7b",
                "size": 4682464166,
                "modified_at": "2026-08-19T10:00:00Z",
                "details": {
                    "format": "gguf",
                    "family": "qwen2",
                    "parameter_size": "7.6B",
                    "quantization_level": "Q4_K_M"
                }
            },
            {
                "name": "mistral-nemo:latest",
                "model": "mistral-nemo:latest",
                "size": 7100234120,
                "modified_at": "2026-08-18T14:30:00Z",
                "details": {
                    "format": "gguf",
                    "family": "mistral",
                    "parameter_size": "12.2B",
                    "quantization_level": "Q4_K_M"
                }
            }
        ]
    }


@pytest.fixture
def mock_ollama_empty_tags() -> Dict[str, Any]:
    """Mock data for Ollama running with 0 models."""
    return {"models": []}
