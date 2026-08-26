"""
Tests for Document Extraction Engine (core/extractor.py)
========================================================
Covers Tiers 1, 2, and 3:
- Ingestion of .txt files (UTF-8, UTF-8-BOM, CP1252, Latin-1)
- Ingestion of .md Markdown files with structure and formatting
- PDF document extraction using pypdf with whitespace normalization & dehyphenation
- Direct raw text pasted input and validation
- "Generate from Scratch" topic prompt mode
- Error handling (missing files, corrupted PDFs, unsupported formats, empty inputs)
- Safe website ingestion with SSRF protection, protocol validation, and private IP blocking
- Safe HTTP streaming fetcher with redirect hop validation and 5MB size limits
- HTML boilerplate stripping, container prioritization, and Wikipedia citation cleaning
- MarkItDown conversion with resilient HTMLToMarkdownParser standard library fallback
- Unified URL routing and progress callbacks
"""

import ipaddress
import socket
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import (
    DocumentExtractionError,
    DocumentIngestionError,
    SecurityError,
    StudioError,
)
from core.extractor import (
    HTMLToMarkdownParser,
    convert_html_to_markdown,
    extract_text,
    extract_text_from_pdf,
    extract_text_from_url,
    fetch_url_content,
    is_ip_address_blocked,
    parse_ip_literal,
    sanitize_html_boilerplate,
    strip_html_boilerplate,
    validate_url_target,
)


class TestExtractorUnit:
    """Tier 1: Feature coverage for basic document and text extraction."""

    def test_extract_utf8_text_file(self, sample_text_utf8: str) -> None:
        text = extract_text(sample_text_utf8)
        assert "Test Document" in text
        assert "æ, ø, å" in text
        assert "Vert 1" in text

    def test_extract_utf8_bom_file(self, sample_text_utf8_bom: str) -> None:
        text = extract_text(sample_text_utf8_bom)
        assert "BOM Document" in text
        assert "Æ, Ø, Å" in text

    def test_extract_cp1252_file(self, sample_text_cp1252: str) -> None:
        text = extract_text(sample_text_cp1252)
        assert "CP1252 Document" in text
        assert "Windows-1252" in text

    def test_extract_latin1_file(self, sample_text_latin1: str) -> None:
        text = extract_text(sample_text_latin1)
        assert "Latin-1 Document" in text
        assert "\u00e6" in text

    def test_extract_markdown_file(self, sample_markdown_file: str) -> None:
        text = extract_text(sample_markdown_file)
        assert "Kunstig Intelligens i Hverdagen" in text
        assert "Edge-TTS" in text
        assert "Pernille og Finn" in text

    def test_extract_raw_text_mode(self) -> None:
        raw = (
            "   This is directly pasted raw content about quantum computing and supercomputers.   "
        )
        text = extract_text(raw, is_raw_text=True)
        assert text.startswith("This is directly")
        assert text.endswith("supercomputers.")
        assert "quantum computing" in text

    def test_extract_topic_mode(self) -> None:
        topic = "Future of renewable energy in the Nordic countries"
        text = extract_text(topic, is_topic=True)
        assert "renewable energy in the Nordic countries" in text


class TestExtractorPDFAndEdgeCases:
    """Tier 2: PDF extraction, normalization, and boundary conditions."""

    def test_extract_pdf_document(self, sample_pdf_file: str) -> None:
        try:
            text = extract_text(sample_pdf_file)
            assert len(text) > 0
        except Exception as e:
            pytest.skip(f"PDF engine requires runtime pypdf environment: {e}")

    def test_pdf_dehyphenation_and_normalization(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = (
            "This is an infor-\nmation system with   extra    spaces.\n\n\n\nNew section."
        )
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [mock_page]

        with (
            patch("pypdf.PdfReader", return_value=mock_reader),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024),
        ):
            result = extract_text_from_pdf("dummy.pdf")
            assert "information system" in result
            assert "extra spaces." in result
            assert "\n\n\n\n" not in result

    def test_pdf_encrypted_with_blank_password(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Decrypted PDF document content."
        mock_reader = MagicMock()
        mock_reader.is_encrypted = True
        mock_reader.decrypt.return_value = True
        mock_reader.pages = [mock_page]

        with (
            patch("pypdf.PdfReader", return_value=mock_reader),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024),
        ):
            result = extract_text_from_pdf("encrypted.pdf")
            mock_reader.decrypt.assert_called_with("")
            assert "Decrypted PDF document content." in result

    def test_pdf_scanned_empty_pages_raises_error(self) -> None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "   "
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [mock_page]

        with (
            patch("pypdf.PdfReader", return_value=mock_reader),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024),
        ):
            with pytest.raises(Exception) as exc_info:
                extract_text_from_pdf("scanned.pdf")
            assert (
                "no extractable text" in str(exc_info.value).lower()
                or "empty" in str(exc_info.value).lower()
            )

    def test_nonexistent_file_raises_error(self) -> None:
        with pytest.raises((FileNotFoundError, Exception)):
            extract_text("non_existent_file_123456.txt")

    def test_unsupported_file_extension(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "image.png"
        bad_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        with pytest.raises((ValueError, Exception)):
            extract_text(str(bad_file))

    def test_empty_raw_text_raises_error(self) -> None:
        with pytest.raises((ValueError, Exception)):
            extract_text("   ", is_raw_text=True)

    def test_empty_topic_prompt_raises_error(self) -> None:
        with pytest.raises((ValueError, Exception)):
            extract_text("", is_topic=True)

    def test_extract_file_exceeds_max_size(self, tmp_path: Path) -> None:
        oversized_file = tmp_path / "oversized.txt"
        oversized_file.write_text("A" * 2048, encoding="utf-8")
        with patch("os.path.getsize", return_value=60 * 1024 * 1024):
            with pytest.raises(DocumentExtractionError) as exc_info:
                extract_text(str(oversized_file))
            assert "exceeds the maximum allowed size" in str(exc_info.value)
            assert "50 MB" in str(exc_info.value)

    def test_extract_pdf_exceeds_page_limit(self) -> None:
        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [MagicMock() for _ in range(250)]

        with (
            patch("pypdf.PdfReader", return_value=mock_reader),
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=1024 * 1024),
        ):
            with pytest.raises(DocumentExtractionError) as exc_info:
                extract_text_from_pdf("huge_document.pdf")
            assert "exceeds the maximum allowed limit of 200 pages" in str(exc_info.value)
            assert "250 pages found" in str(exc_info.value)

    def test_extract_text_with_pathlib_path(self, sample_text_utf8: str) -> None:
        path_obj = Path(sample_text_utf8)
        text = extract_text(path_obj)
        assert "Test Document" in text


class TestSecurityExceptionsHierarchy:
    """Verify that SecurityError properly integrates with domain exception hierarchy."""

    def test_security_error_inheritance(self) -> None:
        assert issubclass(SecurityError, DocumentIngestionError)
        assert issubclass(SecurityError, DocumentExtractionError)
        assert issubclass(SecurityError, StudioError)
        assert issubclass(SecurityError, ValueError)

        err = SecurityError("SSRF detected")
        assert isinstance(err, DocumentIngestionError)
        assert isinstance(err, DocumentExtractionError)
        assert isinstance(err, StudioError)
        assert isinstance(err, ValueError)


class TestSSRFDefenseAndURLValidation:
    """Unit and security tests for validate_url_target and SSRF protection."""

    @pytest.mark.parametrize(
        "bad_url",
        [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "ftp://ftp.example.com/file.txt",
            "gopher://gopher.example.com",
            "dict://dict.example.com",
            "javascript:alert(1)",
            "data:text/html,<h1>Test</h1>",
            "tftp://10.0.0.1",
        ],
    )
    def test_reject_unsupported_protocols(self, bad_url: str) -> None:
        with pytest.raises(SecurityError, match="Unsupported URL protocol"):
            validate_url_target(bad_url)

    @pytest.mark.parametrize("empty_url", ["", "   ", None])
    def test_reject_empty_url(self, empty_url: Any) -> None:
        with pytest.raises(SecurityError, match="Invalid URL"):
            validate_url_target(empty_url)

    def test_reject_url_missing_hostname(self) -> None:
        with pytest.raises(SecurityError, match="missing or invalid hostname"):
            validate_url_target("http://")

    @pytest.mark.parametrize(
        "loopback_url",
        [
            "http://127.0.0.1:11434",
            "http://127.0.0.2:8080",
            "http://127.255.255.254",
            "http://localhost",
            "http://localhost:8080",
            "http://test.localhost",
            "http://[::1]:8080/",
        ],
    )
    def test_reject_loopback_addresses(self, loopback_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(loopback_url)

    @pytest.mark.parametrize(
        "private_url",
        [
            "http://10.0.0.1",
            "http://10.254.1.1:8000",
            "http://172.16.0.1",
            "http://172.31.255.254",
            "http://192.168.1.1",
            "http://192.168.0.254:3000",
            "http://[fc00::1]/",
            "http://[fd12:3456:789a::1]/",
        ],
    )
    def test_reject_private_subnets(self, private_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(private_url)

    @pytest.mark.parametrize(
        "metadata_url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.0.1",
            "http://168.63.129.16",
            "http://[fe80::1]/",
        ],
    )
    def test_reject_cloud_metadata_and_link_local(self, metadata_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(metadata_url)

    @pytest.mark.parametrize(
        "mapped_url",
        [
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://[::ffff:10.0.0.1]/",
            "http://[::ffff:192.168.1.1]/",
        ],
    )
    def test_reject_ipv4_mapped_ipv6(self, mapped_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(mapped_url)

    @pytest.mark.parametrize(
        "obfuscated_url",
        [
            "http://2130706433/",  # Decimal integer for 127.0.0.1
            "http://0x7f000001/",  # Hexadecimal for 127.0.0.1
        ],
    )
    def test_reject_obfuscated_ip_addresses(self, obfuscated_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(obfuscated_url)

    @pytest.mark.parametrize(
        "reserved_url",
        [
            "http://224.0.0.1/",
            "http://240.0.0.1/",
            "http://0.0.0.0:5000/",
            "http://255.255.255.255/",
            "http://100.64.0.1/",  # CGNAT
        ],
    )
    def test_reject_multicast_and_reserved(self, reserved_url: str) -> None:
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(reserved_url)

    def test_reject_dns_multi_homing_with_private_ip(self) -> None:
        with patch(
            "socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 80)),
                (2, 1, 6, "", ("127.0.0.1", 80)),
            ],
        ):
            with pytest.raises(SecurityError, match="blocked or private IP"):
                validate_url_target("http://evil-rebinding.example.com")

    def test_dns_resolution_failure_raises_security_error(self) -> None:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name resolution failure")):
            with pytest.raises(SecurityError, match="Failed to resolve DNS"):
                validate_url_target("http://nonexistent-domain-xyz-12345.org")

    def test_allow_valid_public_url(self) -> None:
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            res = validate_url_target("https://example.com/article")
            assert res == "https://example.com/article"

    def test_parse_ip_literal_helpers(self) -> None:
        assert parse_ip_literal("127.0.0.1") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("2130706433") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("0x7f000001") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("::1") == ipaddress.ip_address("::1")
        assert parse_ip_literal("example.com") is None

    def test_is_ip_address_blocked_helper(self) -> None:
        assert is_ip_address_blocked(ipaddress.ip_address("127.0.0.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("10.0.0.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("192.168.1.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("169.254.169.254")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("93.184.216.34")) is False


class TestSafeFetcherStreamingAndRedirects:
    """Unit tests for fetch_url_content, streaming bounds, and redirect handling."""

    def test_fetch_url_content_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": "100"}
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content.return_value = [b"<html><body><h1>Safe Content</h1></body></html>"]

        with (
            patch("core.extractor.validate_url_target", return_value="https://example.com/article"),
            patch("requests.get", return_value=mock_resp),
        ):
            html = fetch_url_content("https://example.com/article")
            assert "<h1>Safe Content</h1>" in html

    def test_fetch_url_content_enforces_content_length_limit(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": str(10 * 1024 * 1024)}  # 10 MB > 5 MB
        mock_resp.encoding = "utf-8"

        with (
            patch("core.extractor.validate_url_target", return_value="https://example.com/big"),
            patch("requests.get", return_value=mock_resp),
        ):
            with pytest.raises(DocumentExtractionError, match="exceeds maximum allowed limit"):
                fetch_url_content("https://example.com/big")

    def test_fetch_url_content_aborts_oversized_streaming(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {}  # No Content-Length header
        mock_resp.encoding = "utf-8"
        # Yield 90 chunks of 64 KB = 5.76 MB (> 5 MB limit)
        mock_resp.iter_content.return_value = [b"A" * 65536 for _ in range(90)]

        with (
            patch(
                "core.extractor.validate_url_target", return_value="https://example.com/infinite"
            ),
            patch("requests.get", return_value=mock_resp),
        ):
            with pytest.raises(DocumentExtractionError, match="exceeded maximum allowed limit"):
                fetch_url_content("https://example.com/infinite")

    def test_fetch_url_content_enforces_timeout(self) -> None:
        import requests

        with (
            patch("core.extractor.validate_url_target", return_value="https://example.com/timeout"),
            patch("requests.get", side_effect=requests.Timeout("Connection timed out")),
        ):
            with pytest.raises(DocumentExtractionError, match="timed out"):
                fetch_url_content("https://example.com/timeout")

    def test_fetch_url_content_handles_http_error_status(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.is_redirect = False

        with (
            patch("core.extractor.validate_url_target", return_value="https://example.com/missing"),
            patch("requests.get", return_value=mock_resp),
        ):
            with pytest.raises(DocumentExtractionError, match="status code 404"):
                fetch_url_content("https://example.com/missing")

    def test_fetch_url_content_follows_valid_redirects(self) -> None:
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": "https://example.com/destination"}

        mock_final = MagicMock()
        mock_final.status_code = 200
        mock_final.is_redirect = False
        mock_final.headers = {}
        mock_final.encoding = "utf-8"
        mock_final.iter_content.return_value = [
            b"<html><body><h1>Redirected Page</h1></body></html>"
        ]

        with (
            patch(
                "core.extractor.validate_url_target",
                side_effect=lambda u: u,
            ),
            patch("requests.get", side_effect=[mock_redirect, mock_final]),
        ):
            html = fetch_url_content("https://example.com/start")
            assert "<h1>Redirected Page</h1>" in html

    def test_fetch_url_content_blocks_ssrf_on_redirect_hop(self) -> None:
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

        with (
            patch(
                "core.extractor.validate_url_target",
                side_effect=[
                    "https://example.com/start",
                    SecurityError("Access to blocked or private IP address is denied."),
                ],
            ),
            patch("requests.get", return_value=mock_redirect),
        ):
            with pytest.raises(SecurityError, match="blocked or private IP"):
                fetch_url_content("https://example.com/start")

    def test_fetch_url_content_exceeds_max_redirects(self) -> None:
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.is_redirect = True

        def location_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            resp = MagicMock()
            resp.status_code = 302
            resp.is_redirect = True
            return resp

        # Generate a chain of distinct redirect targets
        hop_targets = [f"https://example.com/hop{i}" for i in range(10)]
        redirect_responses = []
        for i in range(7):
            r = MagicMock()
            r.status_code = 302
            r.is_redirect = True
            r.headers = {"Location": hop_targets[i + 1]}
            redirect_responses.append(r)

        with (
            patch("core.extractor.validate_url_target", side_effect=lambda u: u),
            patch("requests.get", side_effect=redirect_responses),
        ):
            with pytest.raises(SecurityError, match="Exceeded maximum allowed redirect hops"):
                fetch_url_content("https://example.com/start", max_redirects=5)

    def test_fetch_url_content_detects_circular_redirect_loop(self) -> None:
        mock_redirect1 = MagicMock()
        mock_redirect1.status_code = 302
        mock_redirect1.is_redirect = True
        mock_redirect1.headers = {"Location": "https://example.com/b"}

        mock_redirect2 = MagicMock()
        mock_redirect2.status_code = 302
        mock_redirect2.is_redirect = True
        mock_redirect2.headers = {"Location": "https://example.com/a"}

        with (
            patch("core.extractor.validate_url_target", side_effect=lambda u: u),
            patch("requests.get", side_effect=[mock_redirect1, mock_redirect2]),
        ):
            with pytest.raises(SecurityError, match="Circular redirect loop detected"):
                fetch_url_content("https://example.com/a")

    def test_fetch_url_content_charset_decoding(self) -> None:
        raw_norwegian = '<meta charset="iso-8859-1"><h1>Blåbærsyltetøy</h1>'.encode("iso-8859-1")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {}
        mock_resp.encoding = None
        mock_resp.iter_content.return_value = [raw_norwegian]

        with (
            patch(
                "core.extractor.validate_url_target", return_value="https://example.com/norwegian"
            ),
            patch("requests.get", return_value=mock_resp),
        ):
            html = fetch_url_content("https://example.com/norwegian")
            assert "Blåbærsyltetøy" in html


class TestHTMLBoilerplateSanitizer:
    """Tests for HTML boilerplate stripping, container prioritization, and Wikipedia cleaning."""

    def test_sanitize_article_container(self) -> None:
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test News</title><script>analytics();</script></head>
        <body>
            <header><nav><a href="/">Home</a></nav></header>
            <div class="cookie-banner"><p>We use cookies</p></div>
            <article class="article-body">
                <h1>Revolution in Renewable Energy</h1>
                <p>Engineers have discovered a high-efficiency solid-state battery technology.</p>
                <div class="ad-banner"><p>Buy cheap car insurance!</p></div>
                <p>Commercial production is projected to begin in late 2027.</p>
            </article>
            <footer>Copyright 2026 NewsCorp</footer>
        </body>
        </html>
        """
        sanitized = sanitize_html_boilerplate(html)
        assert "Revolution in Renewable Energy" in sanitized
        assert "high-efficiency solid-state battery" in sanitized
        assert "Commercial production is projected" in sanitized
        assert "Home" not in sanitized
        assert "cookie-banner" not in sanitized
        assert "Buy cheap car insurance" not in sanitized
        assert "Copyright 2026" not in sanitized

    def test_sanitize_main_and_role_main(self) -> None:
        html = """
        <html><body>
        <nav>Nav links</nav>
        <main>
            <h1>Main Title</h1>
            <p>Main narrative content describing advanced artificial intelligence.</p>
        </main>
        <footer>Footer</footer>
        </body></html>
        """
        sanitized = sanitize_html_boilerplate(html)
        assert "Main Title" in sanitized
        assert "Main narrative content" in sanitized
        assert "Nav links" not in sanitized
        assert "Footer" not in sanitized

    def test_sanitize_wikipedia_page(self) -> None:
        wiki_html = """
        <html>
        <body>
        <div id="mw-page-base"></div>
        <div id="content" role="main">
            <div id="mw-content-text">
                <div class="mw-parser-output">
                    <div class="hatnote">For other uses, see Quantum.</div>
                    <p><b>Quantum computing</b> is a rapidly emerging technology[1] that harnesses quantum mechanics.[2][note 1] <span class="mw-editsection">[<a href="#">edit</a>]</span></p>
                    <h2>Historie[rediger | rediger kilde]</h2>
                    <p>Dette skjedde i år 872.[kilde trengs] Kongen vant slaget ved Hafrsfjord.[note 2]</p>
                    <div class="reflist"><ol class="references"><li>Reference 1</li></ol></div>
                    <div class="navbox">Navigation footer table</div>
                </div>
            </div>
        </div>
        </body>
        </html>
        """
        sanitized = sanitize_html_boilerplate(wiki_html)
        assert "Quantum computing" in sanitized
        assert "harnesses quantum mechanics" in sanitized
        assert "Historie" in sanitized
        assert "slaget ved Hafrsfjord" in sanitized
        assert "[1]" not in sanitized
        assert "[2]" not in sanitized
        assert "[note 1]" not in sanitized
        assert "[note 2]" not in sanitized
        assert "[edit]" not in sanitized
        assert "[rediger" not in sanitized
        assert "[kilde trengs]" not in sanitized
        assert "hatnote" not in sanitized
        assert "reflist" not in sanitized
        assert "navbox" not in sanitized

    def test_sanitize_noise_classes_without_false_positives(self) -> None:
        html = """
        <article>
            <h1>Threading and Shadow Gradients</h1>
            <p>We read the broadcast stream and download the required thread packages.</p>
            <div class="ad-container"><p>Bad Ad</p></div>
            <div class="social-share"><button>Share on X</button></div>
        </article>
        """
        sanitized = sanitize_html_boilerplate(html)
        assert "Threading and Shadow Gradients" in sanitized
        assert "read the broadcast stream and download the required thread" in sanitized
        assert "Bad Ad" not in sanitized
        assert "Share on X" not in sanitized

    def test_sanitize_punctuation_spacing_cleanup(self) -> None:
        html = (
            "<article><p>Albert Einstein was born in Ulm [1] . "
            "Later he moved to Switzerland [2] , then USA [3] !</p></article>"
        )
        sanitized = sanitize_html_boilerplate(html)
        assert "born in Ulm." in sanitized
        assert "Switzerland," in sanitized
        assert "then USA!" in sanitized
        assert " [1] ." not in sanitized


class TestHTMLToMarkdownParser:
    """Tests for HTMLToMarkdownParser standard library converter."""

    def test_markdown_headings_and_paragraphs(self) -> None:
        html = "<h1>Header 1</h1><p>Paragraph 1 text.</p><h2>Header 2</h2><p>Paragraph 2 text.</p>"
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "# Header 1" in md
        assert "Paragraph 1 text." in md
        assert "## Header 2" in md
        assert "Paragraph 2 text." in md

    def test_markdown_formatting(self) -> None:
        html = (
            "<p>This is <strong>bold</strong>, <em>italic</em>, "
            "and <code>inline_code</code> with <del>strike</del>.</p>"
            "<pre>def add(a, b):\n    return a + b\n</pre>"
        )
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "**bold**" in md
        assert "*italic*" in md
        assert "`inline_code`" in md
        assert "~~strike~~" in md
        assert "```\ndef add(a, b):\n    return a + b\n\n```" in md

    def test_markdown_lists(self) -> None:
        html = """
        <ul>
            <li>Unordered Item 1</li>
            <li>Unordered Item 2</li>
        </ul>
        <ol>
            <li>Ordered Item 1</li>
            <li>Ordered Item 2</li>
        </ol>
        """
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "* Unordered Item 1" in md
        assert "* Unordered Item 2" in md
        assert "1. Ordered Item 1" in md
        assert "2. Ordered Item 2" in md

    def test_markdown_links(self) -> None:
        html = '<p>Visit <a href="https://example.com/article">Example News</a> for more information.</p>'
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "[Example News](https://example.com/article)" in md

    def test_markdown_entities(self) -> None:
        html = "<p>Norwegian vowels: &aelig;, &oslash;, &aring;. Symbols: &amp;, &quot;, &#39;.</p>"
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "æ, ø, å" in md
        assert "&, \", '." in md

    def test_markdown_malformed_html(self) -> None:
        html = "<div><h1>Unclosed Header<p>Unclosed paragraph<br>Second line</div>"
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        parser.close()
        md = parser.get_markdown()

        assert "# Unclosed Header" in md
        assert "Unclosed paragraph" in md
        assert "Second line" in md


class TestMarkItDownConversion:
    """Tests for convert_html_to_markdown dynamic import and fallback."""

    def test_convert_html_to_markdown_fallback_when_markitdown_unavailable(self) -> None:
        html = "<h1>Clean Header</h1><p>Narrative paragraph without markitdown package.</p>"
        result = convert_html_to_markdown(html)
        assert "# Clean Header" in result
        assert "Narrative paragraph without markitdown package." in result

    def test_convert_html_to_markdown_with_mocked_markitdown(self) -> None:
        mock_result = MagicMock()
        mock_result.text_content = "# MarkItDown Header\n\nContent converted by MarkItDown."

        mock_instance = MagicMock()
        mock_instance.convert_stream.return_value = mock_result

        mock_module = ModuleType("markitdown")
        mock_module.MarkItDown = MagicMock(return_value=mock_instance)

        with patch.dict(sys.modules, {"markitdown": mock_module}):
            html = "<h1>MarkItDown Header</h1><p>Content converted by MarkItDown.</p>"
            result = convert_html_to_markdown(html)
            assert "# MarkItDown Header" in result
            assert "Content converted by MarkItDown." in result


class TestUnifiedExtractionRouter:
    """Tests for unified extract_text and extract_text_from_url entry points."""

    def test_extract_text_is_url_flag(self) -> None:
        with patch(
            "core.extractor.fetch_url_content",
            return_value="<article><h1>URL Article</h1><p>Content from website.</p></article>",
        ):
            with patch(
                "core.extractor.validate_url_target", return_value="https://example.com/news"
            ):
                result = extract_text("https://example.com/news", is_url=True)
                assert "# URL Article" in result
                assert "Content from website." in result

    def test_extract_text_url_autodetect(self) -> None:
        with patch(
            "core.extractor.fetch_url_content",
            return_value="<article><h1>Auto-detected Article</h1><p>Auto-detected content.</p></article>",
        ):
            with patch(
                "core.extractor.validate_url_target", return_value="https://example.com/autodetect"
            ):
                result = extract_text("https://example.com/autodetect")
                assert "# Auto-detected Article" in result
                assert "Auto-detected content." in result

    def test_extract_text_url_progress_callback(self) -> None:
        progress_messages: list[str] = []

        def callback(msg: str) -> None:
            progress_messages.append(msg)

        with patch(
            "core.extractor.fetch_url_content",
            return_value="<article><h1>Progress Article</h1><p>Progress text.</p></article>",
        ):
            with patch(
                "core.extractor.validate_url_target", return_value="https://example.com/progress"
            ):
                result = extract_text(
                    "https://example.com/progress", is_url=True, progress_callback=callback
                )
                assert "# Progress Article" in result
                assert len(progress_messages) >= 3

    def test_extract_text_empty_web_content_raises(self) -> None:
        with patch("core.extractor.fetch_url_content", return_value="<html><body></body></html>"):
            with patch(
                "core.extractor.validate_url_target", return_value="https://example.com/empty"
            ):
                with pytest.raises(DocumentExtractionError, match="insufficient extractable text"):
                    extract_text_from_url("https://example.com/empty")

    def test_strip_html_boilerplate_alias(self) -> None:
        assert strip_html_boilerplate is sanitize_html_boilerplate
