"""
Adversarial Stress Test Suite for SSRF Defense, URL Validation, and Resource Bounding
======================================================================================
Location: tests/test_challenger_m1_ssrf_adversarial.py
Milestone: M1 (Security & SSRF Verification)

Covers empirical stress tests against:
1. SSRF bypass attempts (IPv4/IPv6 literals, hex/decimal obfuscation, link-local, private CIDRs,
   cloud metadata, IPv4-mapped IPv6, protocol manipulation).
2. Redirect attacks (pivoting from public URLs to local Ollama / metadata endpoints,
   redirect loops > 5 hops, circular loops, redirect chains).
3. Resource exhaustion attacks (streaming chunks > 5MB, slow chunk timeouts,
   Content-Length header deception & mismatch).
4. DNS resolution edge cases (multi-homed DNS rebinding with private IP, resolution failures).
"""

import ipaddress
import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.exceptions import DocumentExtractionError, SecurityError
from core.extractor import (
    DEFAULT_MAX_REDIRECTS,
    DEFAULT_MAX_URL_SIZE_BYTES,
    fetch_url_content,
    is_ip_address_blocked,
    parse_ip_literal,
    validate_url_target,
)


class TestSSRFBypassAdversarialMatrix:
    """Adversarial stress-testing of SSRF filter with diverse payload representations."""

    @pytest.mark.parametrize(
        "payload,expected_category",
        [
            ("http://0.0.0.0", "zero_network"),
            ("http://0.0.0.0:8000/api", "zero_network"),
            ("http://127.0.0.1", "loopback_v4"),
            ("http://127.0.0.1:11434/api/generate", "loopback_v4_ollama"),
            ("http://127.0.0.2:8080", "loopback_v4_subnet"),
            ("http://127.255.255.254", "loopback_v4_broadcast"),
            ("http://127.1", "shorthand_ip"),
            ("http://2130706433", "decimal_ip_loopback"),
            ("http://2130706433:11434", "decimal_ip_with_port"),
            ("http://0x7f000001", "hex_ip_loopback"),
            ("http://0x7f000001:11434", "hex_ip_with_port"),
            ("http://[::1]", "loopback_v6"),
            ("http://[::1]:11434", "loopback_v6_with_port"),
            ("http://[::]", "unspecified_v6"),
            ("http://[::ffff:127.0.0.1]", "ipv4_mapped_ipv6_loopback"),
            ("http://[::ffff:127.0.0.1]:11434", "ipv4_mapped_ipv6_ollama"),
            ("http://169.254.169.254", "aws_gcp_metadata"),
            ("http://169.254.169.254/latest/meta-data/", "aws_metadata_path"),
            ("http://169.254.169.253", "cloud_metadata_neighbor"),
            ("http://[::ffff:169.254.169.254]", "ipv4_mapped_metadata"),
            ("http://168.63.129.16", "azure_metadata"),
            ("http://10.0.0.1", "class_a_private"),
            ("http://10.255.255.255", "class_a_broadcast"),
            ("http://172.16.0.1", "class_b_private_start"),
            ("http://172.31.255.255", "class_b_private_end"),
            ("http://192.168.0.1", "class_c_private"),
            ("http://192.168.1.1", "class_c_gateway"),
            ("http://192.168.255.254", "class_c_private_end"),
            ("http://[fe80::1]", "ipv6_link_local"),
            ("http://[fe80::ffff:1]", "ipv6_link_local_high"),
            ("http://[fc00::1]", "ipv6_ula_private"),
            ("http://[fd12:3456:789a::1]", "ipv6_ula_random"),
            ("http://localhost", "hostname_localhost"),
            ("http://localhost:11434", "hostname_localhost_port"),
            ("http://localhost.localdomain", "hostname_localhost_domain"),
            ("http://foo.localhost", "subdomain_localhost"),
            ("http://100.64.0.1", "cgnat_private"),
            ("http://224.0.0.1", "multicast_v4"),
            ("http://255.255.255.255", "limited_broadcast"),
            ("file:///etc/passwd", "scheme_file_unix"),
            ("file:///C:/Windows/win.ini", "scheme_file_win"),
            ("gopher://127.0.0.1:11434", "scheme_gopher"),
            ("ftp://ftp.internal.local", "scheme_ftp"),
            ("dict://dict.internal.local", "scheme_dict"),
            ("tftp://10.0.0.1", "scheme_tftp"),
            ("javascript:alert(1)", "scheme_js"),
            ("data:text/html,test", "scheme_data"),
        ],
    )
    def test_ssrf_blocked_payloads(self, payload: str, expected_category: str) -> None:
        """Every listed SSRF bypass attempt must raise SecurityError."""
        with pytest.raises(SecurityError) as exc_info:
            validate_url_target(payload)
        err_msg = str(exc_info.value)
        assert any(
            phrase in err_msg.lower()
            for phrase in (
                "blocked or private ip",
                "unsupported url protocol",
                "ssrf protection",
                "invalid url",
                "failed to resolve dns",
            )
        ), f"Unexpected error message for {expected_category} ({payload}): {err_msg}"

    def test_direct_ip_literal_helpers_adversarial(self) -> None:
        """Verify internal parsing and classification of edge-case IP literals."""
        assert DEFAULT_MAX_URL_SIZE_BYTES == 5 * 1024 * 1024

        # IP literal parsing across representations
        assert parse_ip_literal("127.0.0.1") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("2130706433") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("0x7f000001") == ipaddress.ip_address("127.0.0.1")
        assert parse_ip_literal("::1") == ipaddress.ip_address("::1")
        assert parse_ip_literal("[::1]") == ipaddress.ip_address("::1")
        assert parse_ip_literal("invalid_host") is None

        # Blocked IP ranges
        assert is_ip_address_blocked(ipaddress.ip_address("0.0.0.0")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("127.0.0.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("169.254.169.254")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("169.254.169.253")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("168.63.129.16")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("10.255.255.255")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("172.31.255.255")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("192.168.1.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("fe80::1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("fc00::1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("::1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("::")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("::ffff:127.0.0.1")) is True
        assert is_ip_address_blocked(ipaddress.ip_address("::ffff:169.254.169.254")) is True

        # Public non-blocked IPs
        assert is_ip_address_blocked(ipaddress.ip_address("93.184.216.34")) is False
        assert is_ip_address_blocked(ipaddress.ip_address("8.8.8.8")) is False
        assert is_ip_address_blocked(ipaddress.ip_address("1.1.1.1")) is False
        assert is_ip_address_blocked(ipaddress.ip_address("2606:4700:4700::1111")) is False

    def test_dns_multi_homing_rebinding_defense(self) -> None:
        """Domain resolving to a mix of public and private IPs must be blocked."""
        with patch(
            "socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ],
        ):
            with pytest.raises(SecurityError, match="blocked or private IP"):
                validate_url_target("https://attacker-rebinding.com")

    def test_dns_resolution_failure_handling(self) -> None:
        """Domain that cannot be resolved must raise SecurityError."""
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            with pytest.raises(SecurityError, match="Failed to resolve DNS"):
                validate_url_target("https://unresolvable-domain-987654321.com")


class TestRedirectAdversarialAttacks:
    """Adversarial stress-testing of redirect hops, SSRF pivoting, and redirect loops."""

    @pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
    def test_redirect_pivot_to_ollama_localhost(self, status_code: int) -> None:
        """A public URL redirecting to 127.0.0.1:11434 must be blocked on the redirect hop."""
        mock_redirect = MagicMock()
        mock_redirect.status_code = status_code
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": "http://127.0.0.1:11434/api/generate"}

        with patch("requests.get", return_value=mock_redirect):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
                with pytest.raises(SecurityError, match="blocked or private IP"):
                    fetch_url_content("https://public-proxy.com/hook")

    @pytest.mark.parametrize("status_code", [301, 302, 307, 308])
    def test_redirect_pivot_to_cloud_metadata(self, status_code: int) -> None:
        """A public URL redirecting to AWS/GCP metadata endpoint must be blocked."""
        mock_redirect = MagicMock()
        mock_redirect.status_code = status_code
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}

        with patch("requests.get", return_value=mock_redirect):
            with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
                with pytest.raises(SecurityError, match="blocked or private IP"):
                    fetch_url_content("https://public-proxy.com/cloud-leak")

    def test_redirect_chain_exceeding_max_hops(self) -> None:
        """A redirect chain exceeding DEFAULT_MAX_REDIRECTS (5) must be halted."""
        responses = []
        for i in range(DEFAULT_MAX_REDIRECTS + 2):
            resp = MagicMock()
            resp.status_code = 302
            resp.is_redirect = True
            resp.headers = {"Location": f"https://example.com/step_{i + 1}"}
            responses.append(resp)

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", side_effect=responses):
                with pytest.raises(SecurityError, match="Exceeded maximum allowed redirect hops"):
                    fetch_url_content("https://example.com/step_0", max_redirects=5)

    def test_circular_redirect_loop_detection(self) -> None:
        """Circular redirect loop (A -> B -> C -> A) must be detected and aborted immediately."""
        resp_a = MagicMock()
        resp_a.status_code = 302
        resp_a.is_redirect = True
        resp_a.headers = {"Location": "https://example.com/node_b"}

        resp_b = MagicMock()
        resp_b.status_code = 302
        resp_b.is_redirect = True
        resp_b.headers = {"Location": "https://example.com/node_c"}

        resp_c = MagicMock()
        resp_c.status_code = 302
        resp_c.is_redirect = True
        resp_c.headers = {"Location": "https://example.com/node_a"}

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", side_effect=[resp_a, resp_b, resp_c]):
                with pytest.raises(SecurityError, match="Circular redirect loop detected"):
                    fetch_url_content("https://example.com/node_a")

    def test_redirect_missing_location_header(self) -> None:
        """A 302 redirect missing the Location header must raise DocumentExtractionError."""
        resp = MagicMock()
        resp.status_code = 302
        resp.is_redirect = True
        resp.headers = {}

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=resp):
                with pytest.raises(DocumentExtractionError, match="missing Location header"):
                    fetch_url_content("https://example.com/broken-redirect")


class TestResourceLimitsAndDeceptionAttacks:
    """Adversarial stress-testing of streaming bounds, timeout enforcement, and deception."""

    def test_content_length_header_oversize_abort(self) -> None:
        """If Content-Length header is > 5MB, abort immediately before reading stream."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": str(10 * 1024 * 1024)}  # 10 MB
        mock_resp.encoding = "utf-8"

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(DocumentExtractionError, match="exceeds maximum allowed limit"):
                    fetch_url_content("https://example.com/huge.html")

    def test_content_length_deception_small_header_large_stream(self) -> None:
        """Attacker sends Content-Length: 100 but streams > 5MB chunk data."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": "100"}  # Deceptive header
        mock_resp.encoding = "utf-8"
        # 100 chunks of 64KB = 6.4 MB (> 5MB limit)
        mock_resp.iter_content.return_value = [b"X" * 65536 for _ in range(100)]

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(DocumentExtractionError, match="exceeded maximum allowed limit"):
                    fetch_url_content("https://example.com/deceptive.html")

    def test_streaming_infinite_chunks_without_content_length(self) -> None:
        """Chunked transfer encoding without Content-Length header exceeding 5MB."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {}  # No Content-Length header
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content.return_value = [b"A" * 65536 for _ in range(90)]  # 5.76 MB

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(DocumentExtractionError, match="exceeded maximum allowed limit"):
                    fetch_url_content("https://example.com/infinite_stream.html")

    def test_slow_chunk_streaming_timeout(self) -> None:
        """Slow server hanging or timing out must trigger DocumentExtractionError."""
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch(
                "requests.get",
                side_effect=requests.Timeout("Read timed out (10.0s)"),
            ):
                with pytest.raises(DocumentExtractionError, match="timed out"):
                    fetch_url_content("https://example.com/slow_server.html", timeout=10.0)

    def test_stream_reading_network_error_interruption(self) -> None:
        """Network drop during stream iteration raises DocumentExtractionError cleanly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {}
        mock_resp.encoding = "utf-8"

        def failing_iter(*args: Any, **kwargs: Any):
            yield b"<html><body>Partial"
            raise requests.ConnectionError("Connection reset by peer during stream")

        mock_resp.iter_content = failing_iter

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(
                    DocumentExtractionError, match="Error while reading response stream"
                ):
                    fetch_url_content("https://example.com/dropped_stream.html")

    def test_empty_content_rejection(self) -> None:
        """Server returning 200 OK with empty body or only whitespace must be rejected."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_redirect = False
        mock_resp.headers = {"Content-Length": "0"}
        mock_resp.encoding = "utf-8"
        mock_resp.iter_content.return_value = [b"   \n\t   "]

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(DocumentExtractionError, match="Fetched empty content"):
                    fetch_url_content("https://example.com/empty.html")

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 500, 502, 503])
    def test_http_error_statuses_rejected(self, status_code: int) -> None:
        """HTTP error status codes must raise DocumentExtractionError."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.is_redirect = False

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_resp):
                with pytest.raises(DocumentExtractionError, match=f"status code {status_code}"):
                    fetch_url_content("https://example.com/status")


class TestAdversarialProtocolAndRedirectionChains:
    """Adversarial stress-testing of credentials in URLs, protocol transitions on redirect, and cumulative timeout."""

    @pytest.mark.parametrize(
        "cred_url",
        [
            "http://user:pass@127.0.0.1:11434/",
            "http://admin:secret@localhost:8000/",
            "http://attacker.com@127.0.0.1:11434/",
            "http://admin:secret@[::1]:11434/",
            "http://root:toor@169.254.169.254/",
            "http://foo:bar@10.0.0.1/",
            "http://user:pass@192.168.1.1:8080/",
        ],
    )
    def test_credential_embedded_ssrf_urls(self, cred_url: str) -> None:
        """Credentials in authority section must not bypass SSRF hostname validation."""
        with pytest.raises(SecurityError, match="blocked or private IP"):
            validate_url_target(cred_url)

    @pytest.mark.parametrize(
        "evil_scheme_target",
        [
            "file:///etc/passwd",
            "file:///C:/Windows/win.ini",
            "gopher://127.0.0.1:11434/_GET%20/api/generate",
            "ftp://ftp.internal.corp/secret.txt",
            "dict://127.0.0.1:2628/",
            "javascript:alert(document.cookie)",
            "data:text/html,<h1>Pwned</h1>",
        ],
    )
    def test_redirect_to_disallowed_protocol(self, evil_scheme_target: str) -> None:
        """A redirect jumping from https to file://, gopher://, ftp:// etc. must be blocked."""
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": evil_scheme_target}

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_redirect):
                with pytest.raises(SecurityError, match="Unsupported URL protocol"):
                    fetch_url_content("https://public-proxy.com/evil-redirect")

    def test_cumulative_redirect_timeout_exceeded(self) -> None:
        """Total execution time exceeding timeout across multiple hops raises DocumentExtractionError."""
        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.is_redirect = True
        mock_redirect.headers = {"Location": "https://example.com/hop2"}

        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("requests.get", return_value=mock_redirect):
                with patch("time.monotonic", side_effect=[0.0, 0.0, 11.0, 11.0]):
                    with pytest.raises(DocumentExtractionError, match="timed out"):
                        fetch_url_content("https://example.com/hop1", timeout=10.0)


class TestAdversarialDOMAndSanitizerFuzzing:
    """Fuzzing DOMTreeBuilder and HTMLToMarkdownParser with deeply nested or malformed structures."""

    def test_deeply_nested_html_hierarchy(self) -> None:
        """Deeply nested HTML (50 levels) must be parsed and sanitized cleanly."""
        from core.extractor import sanitize_html_boilerplate

        nested_html = (
            "<div>" * 50
            + "<article><h1>Nested Content</h1><p>Inside deep DOM</p></article>"
            + "</div>" * 50
        )
        sanitized = sanitize_html_boilerplate(nested_html)
        assert "Nested Content" in sanitized
        assert "Inside deep DOM" in sanitized

    def test_huge_noise_document_insufficient_content(self) -> None:
        """Document filled with 1MB of comments and noise tags results in empty text rejection."""
        from core.extractor import extract_text_from_url

        noise_html = (
            "<html><body><script>" + ("console.log('spam');" * 10000) + "</script></body></html>"
        )
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("core.extractor.fetch_url_content", return_value=noise_html):
                with pytest.raises(DocumentExtractionError, match="insufficient extractable text"):
                    extract_text_from_url("https://example.com/noise.html")
