"""
LocalPodcastLLMStudio - Document Ingestion & Text Extraction Engine
Supports .txt, .md, .pdf files, pasted raw text, scratch topic prompts, and safe website URL ingestion.
"""

import io
import ipaddress
import os
import re
import socket
import time
import urllib.parse
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

import requests

from core.exceptions import DocumentExtractionError, SecurityError

# Safe document ingestion bounds to protect against memory exhaustion (DoS)
DEFAULT_MAX_FILE_SIZE_MB: int = 50
DEFAULT_MAX_FILE_SIZE_BYTES: int = DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024  # 52,428,800 bytes
DEFAULT_MAX_PDF_PAGES: int = 200

# Safe URL fetcher and SSRF protection bounds
DEFAULT_MAX_URL_SIZE_BYTES: int = 5 * 1024 * 1024  # 5,242,880 bytes (5 MB)
DEFAULT_FETCH_TIMEOUT_SECONDS: float = 10.0
DEFAULT_MAX_REDIRECTS: int = 5
DEFAULT_USER_AGENT: str = (
    "LocalPodcastLLMStudio/1.0 (Safe Ingestion Engine; +https://github.com/LocalPodcastLLMStudio)"
)

ALLOWED_URL_SCHEMES: tuple[str, ...] = ("http", "https")

# Comprehensive IP network CIDR blocking rules for SSRF defense
BLOCKED_IP_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),  # IPv4 private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # IPv4 private Class B
    ipaddress.ip_network("192.168.0.0/16"),  # IPv4 private Class C
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local & cloud metadata
    ipaddress.ip_network("168.63.129.16/32"),  # Azure metadata endpoint
    ipaddress.ip_network("0.0.0.0/8"),  # Current network
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-Grade NAT (CGNAT)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved / broadcast
    ipaddress.ip_network("255.255.255.255/32"),  # Limited broadcast
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("::/128"),  # IPv6 unspecified
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local Address (ULA)
    ipaddress.ip_network("fe80::/10"),  # IPv6 Link-Local
    ipaddress.ip_network("ff00::/8"),  # IPv6 Multicast
    ipaddress.ip_network("2001:db8::/32"),  # IPv6 Documentation
)

# Precompiled regular expressions for text normalization performance
_RE_HYPHEN_BREAK = re.compile(r"(\b\w+)-\n(\w+\b)")
_RE_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_RE_LINE_WHITESPACE = re.compile(r" ?\n ?")
_RE_CONSECUTIVE_NEWLINES = re.compile(r"\n{3,}")

# Void HTML tags with no closing tag in HTML5
VOID_TAGS: set[str] = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

# Tags whose entire subtree (content and child nodes) must be stripped
NOISE_TAGS: set[str] = {
    "aside",
    "button",
    "canvas",
    "dialog",
    "footer",
    "form",
    "head",
    "header",
    "iframe",
    "nav",
    "noscript",
    "script",
    "select",
    "style",
    "svg",
    "template",
    "textarea",
}

# Token-boundary regex matching noise classes and IDs
NOISE_ATTR_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|[\s\-_])(?:"
    r"ad|ads|advert|advertising|advertisement|adsense|adbox|sponsor|sponsored|"
    r"cookie|cookies|cookie-consent|cookie-banner|cookie-notice|gdpr|"
    r"popup|pop-up|modal|overlay|toast|"
    r"navbox|vertical-navbox|navbar|"
    r"hatnote|"
    r"reference|references|reflist|"
    r"mw-editsection|mw-jump-link|mw-indicators|"
    r"noprint|"
    r"sidebar|side-bar|widget-area|"
    r"share-buttons|social-share|social-links|share-bar|sharing|"
    r"comments|comment-list|comment-form|disqus|respond|"
    r"related-posts|recommended"
    r")(?:[\s\-_]|$)",
    re.IGNORECASE,
)

# Wikipedia citation and edit reference markers pattern
WIKIPEDIA_CITATION_PATTERN: re.Pattern[str] = re.compile(
    r"\[\s*(?:"
    r"\d+(?:\s*[,–-]\s*\d+)*|"
    r"[a-z]|"
    r"(?:note|nb)\s*\d+|"
    r"citation needed|kilde trengs|trenger referanse|"
    r"clarification needed|dead link|page needed|"
    r"when\?|who\?|failed verification|"
    r"edit|rediger(?:\s*[|/]\s*rediger\s*kilde)?|rediger\s*kilde"
    r")\s*\]",
    re.IGNORECASE,
)

_RE_ORPHAN_PUNCTUATION_SPACE: re.Pattern[str] = re.compile(r" +([.,;:!?])")


def normalize_extracted_text(raw_text: str) -> str:
    """
    Cleans and normalizes extracted text:
    1. Normalizes line endings to '\\n'.
    2. Reconnects hyphenated line-breaks (e.g. 'auto-\\nmatic' -> 'automatic').
    3. Normalizes non-breaking and Unicode spaces to standard ASCII spaces.
    4. Cleans horizontal whitespace.
    5. Collapses 3+ consecutive newlines to 2.
    """
    if not raw_text:
        return ""

    # PERFORMANCE OPTIMIZATION: Normalize line breaks first so hyphenated breaks
    # with \r\n are handled consistently, and use fast-path substring checks before
    # executing expensive C-regex pattern substitutions (up to 2-3x speedup on large text).
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    # Rejoin hyphenated line-breaks only if hyphen-newline sequence exists
    if "-\n" in text:
        text = _RE_HYPHEN_BREAK.sub(r"\1\2", text)

    # Replace non-breaking space and other unicode space separators if present
    if "\xa0" in text or "\u200b" in text or "\ufeff" in text:
        text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    # Clean multiple horizontal spaces and tabs while preserving newlines
    if "  " in text or "\t" in text:
        text = _RE_HORIZONTAL_WHITESPACE.sub(" ", text)

    # Clean trailing or leading whitespace around newlines
    if " \n" in text or "\n " in text:
        text = _RE_LINE_WHITESPACE.sub("\n", text)

    # Collapse excessive newlines (3 or more)
    if "\n\n\n" in text:
        text = _RE_CONSECUTIVE_NEWLINES.sub("\n\n", text)

    return text.strip()


def is_ip_address_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Evaluates whether an IP address belongs to loopback, private, link-local,
    cloud metadata, multicast, reserved, or non-globally routable spaces.
    Handles IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1) transparently.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_ip_address_blocked(ip.ipv4_mapped)

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    for net in BLOCKED_IP_NETWORKS:
        if ip.version == net.version and ip in net:
            return True

    return False


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """
    Attempts to parse a hostname as an IP literal across standard dot-decimal,
    bracketed IPv6, plain integer, and hexadecimal representations.
    """
    host_clean = host.strip("[]")
    try:
        return ipaddress.ip_address(host_clean)
    except ValueError:
        pass

    if host_clean.isdigit():
        try:
            return ipaddress.ip_address(int(host_clean))
        except (ValueError, OverflowError):
            pass

    if host_clean.lower().startswith("0x"):
        try:
            return ipaddress.ip_address(int(host_clean, 16))
        except (ValueError, OverflowError):
            pass

    return None


def validate_url_target(url: str) -> str:
    """
    Validates a URL against SSRF and protocol manipulation attacks:
    1. Enforces http:// or https:// protocol allowlist.
    2. Parses hostname and checks direct IP literals (decimal, hex, IPv6).
    3. Resolves DNS records via socket.getaddrinfo.
    4. Validates all resolved IP addresses against loopback, private, link-local,
       cloud metadata, and reserved networks.

    Returns:
        Validated and cleaned URL string.

    Raises:
        SecurityError: If URL violates protocol rules or resolves to blocked IP space.
    """
    if not url or not isinstance(url, str):
        raise SecurityError("Invalid URL: URL must be a non-empty string.")

    cleaned_url = url.strip()
    if not cleaned_url:
        raise SecurityError("Invalid URL: URL must be a non-empty string.")

    try:
        parsed = urllib.parse.urlsplit(cleaned_url)
    except Exception as exc:
        raise SecurityError(f"Malformed URL '{cleaned_url}': {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise SecurityError(
            f"Unsupported URL protocol '{scheme}'. Only 'http' and 'https' protocols are supported."
        )

    hostname = parsed.hostname
    if not hostname or not hostname.strip():
        raise SecurityError(f"Invalid URL: missing or invalid hostname in '{cleaned_url}'.")

    hostname_clean = hostname.strip().rstrip(".")
    if hostname_clean.lower() in (
        "localhost",
        "localhost.localdomain",
    ) or hostname_clean.lower().endswith(".localhost"):
        raise SecurityError(
            f"Access to blocked or private IP address for hostname '{hostname_clean}' is denied (SSRF protection)."
        )

    ip_literal = parse_ip_literal(hostname_clean)
    if ip_literal is not None:
        if is_ip_address_blocked(ip_literal):
            raise SecurityError(
                f"Access to blocked or private IP address '{ip_literal}' is denied (SSRF protection)."
            )
        return cleaned_url

    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        addr_info = socket.getaddrinfo(hostname_clean, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, socket.herror, OSError) as exc:
        raise SecurityError(
            f"Failed to resolve DNS for hostname '{hostname_clean}': {exc}"
        ) from exc

    if not addr_info:
        raise SecurityError(f"No IP addresses resolved for hostname '{hostname_clean}'.")

    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SecurityError(
                f"Resolved invalid IP address '{ip_str}' for hostname '{hostname_clean}'."
            ) from exc

        if is_ip_address_blocked(ip_obj):
            raise SecurityError(
                f"Access to blocked or private IP address '{ip_obj}' (resolved from '{hostname_clean}') is denied (SSRF protection)."
            )

    return cleaned_url


def detect_and_decode_html(raw_bytes: bytes, header_encoding: str | None = None) -> str:
    """
    Decodes raw HTML bytes into a string with resilient multi-encoding fallback.
    Checks HTTP response header charset, HTML <meta charset>, and standard encodings.
    """
    if not raw_bytes:
        return ""

    if header_encoding and header_encoding.lower() not in ("iso-8859-1", "ascii"):
        try:
            return raw_bytes.decode(header_encoding)
        except (UnicodeDecodeError, LookupError):
            pass

    sample = raw_bytes[:4096]
    match = re.search(rb"""<meta[^>]+charset=["']?([a-zA-Z0-9_\-]+)""", sample, re.IGNORECASE)
    if match:
        meta_enc = match.group(1).decode("ascii", errors="ignore").strip()
        try:
            return raw_bytes.decode(meta_enc)
        except (UnicodeDecodeError, LookupError):
            pass

    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1", "iso-8859-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue

    return raw_bytes.decode("utf-8", errors="replace")


def fetch_url_content(
    url: str,
    timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    max_size_bytes: int = DEFAULT_MAX_URL_SIZE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Safely fetches HTML content from a website with SSRF protection,
    manual redirect hop validation, streaming chunk size bounds, and timeout enforcement.

    Args:
        url: The HTTP/HTTPS target URL.
        timeout: Total timeout in seconds across all operations.
        max_size_bytes: Maximum allowed downloaded content size in bytes (default: 5 MB).
        max_redirects: Maximum allowed redirect hops (default: 5).
        progress_callback: Optional status callback function.

    Returns:
        Decoded HTML content string.

    Raises:
        SecurityError: If URL or any redirect target resolves to blocked IP space or violates protocols.
        DocumentExtractionError: If download fails, times out, or exceeds max_size_bytes.
    """
    current_url = url.strip() if isinstance(url, str) else ""
    visited_urls: set[str] = set()
    deadline = time.monotonic() + timeout

    for hop in range(max_redirects + 1):
        remaining_time = max(0.1, deadline - time.monotonic())
        if remaining_time <= 0.1 and hop > 0:
            raise DocumentExtractionError(
                f"Fetching URL '{url}' timed out after {timeout:.1f} seconds."
            )

        validated_url = validate_url_target(current_url)
        visited_urls.add(validated_url)

        if progress_callback:
            if hop == 0:
                progress_callback(f"Connecting to {urllib.parse.urlsplit(validated_url).netloc}...")
            else:
                progress_callback(
                    f"Following redirect ({hop}/{max_redirects}) to {urllib.parse.urlsplit(validated_url).netloc}..."
                )

        try:
            response = requests.get(
                validated_url,
                stream=True,
                allow_redirects=False,
                timeout=remaining_time,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
        except requests.Timeout as exc:
            raise DocumentExtractionError(
                f"Connection to '{validated_url}' timed out after {timeout:.1f}s."
            ) from exc
        except requests.RequestException as exc:
            raise DocumentExtractionError(
                f"Failed to fetch content from '{validated_url}': {exc}"
            ) from exc

        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            if hop >= max_redirects:
                raise SecurityError(
                    f"Exceeded maximum allowed redirect hops ({max_redirects}) while fetching '{url}'."
                )

            location = response.headers.get("Location")
            if not location:
                raise DocumentExtractionError(
                    f"HTTP {response.status_code} redirect response from '{validated_url}' missing Location header."
                )

            next_url = urllib.parse.urljoin(validated_url, location)
            if next_url in visited_urls:
                raise SecurityError(
                    f"Circular redirect loop detected: '{next_url}' was already visited."
                )

            current_url = next_url
            continue

        if response.status_code != 200:
            raise DocumentExtractionError(
                f"HTTP request to '{validated_url}' failed with status code {response.status_code}."
            )

        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            cl_int = int(content_length)
            if cl_int > max_size_bytes:
                raise DocumentExtractionError(
                    f"Target URL '{validated_url}' response size ({cl_int / (1024 * 1024):.1f} MB) exceeds maximum allowed limit of {max_size_bytes / (1024 * 1024):.1f} MB."
                )

        chunks: list[bytes] = []
        downloaded_bytes: int = 0
        chunk_size: int = 65536

        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > max_size_bytes:
                        raise DocumentExtractionError(
                            f"Downloaded content from '{validated_url}' exceeded maximum allowed limit of {max_size_bytes / (1024 * 1024):.1f} MB."
                        )
                    chunks.append(chunk)
        except requests.RequestException as exc:
            raise DocumentExtractionError(
                f"Error while reading response stream from '{validated_url}': {exc}"
            ) from exc

        raw_bytes = b"".join(chunks)
        if not raw_bytes or len(raw_bytes.strip()) == 0:
            raise DocumentExtractionError(f"Fetched empty content from '{validated_url}'.")

        return detect_and_decode_html(raw_bytes, response.encoding)

    raise SecurityError(f"Failed to fetch '{url}': maximum redirect hops exceeded.")


class DOMNode:
    """Lightweight DOM node representing an element or text chunk."""

    __slots__ = ("attrs", "children", "is_text", "parent", "tag", "text")

    def __init__(
        self,
        tag: str | None = None,
        attrs: list[tuple[str, str | None]] | None = None,
        is_text: bool = False,
        text: str = "",
    ):
        self.tag: str = tag.lower() if tag else ""
        self.attrs: dict[str, str] = {k.lower(): (v or "") for k, v in attrs} if attrs else {}
        self.parent: DOMNode | None = None
        self.children: list[DOMNode] = []
        self.text: str = text
        self.is_text: bool = is_text

    def append_child(self, child: "DOMNode") -> None:
        child.parent = self
        self.children.append(child)

    def get_attr(self, key: str) -> str:
        return self.attrs.get(key.lower(), "")

    def has_class(self, class_name: str) -> bool:
        classes = self.attrs.get("class", "").split()
        return class_name.lower() in (c.lower() for c in classes)

    def get_text_content(self) -> str:
        if self.is_text:
            return self.text
        if _is_noise_node(self):
            return ""
        return "".join(c.get_text_content() for c in self.children)


class DOMTreeBuilder(HTMLParser):
    """Parses HTML into a lightweight DOM tree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: DOMNode = DOMNode(tag="[root]")
        self.current: DOMNode = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DOMNode(tag=tag, attrs=attrs)
        self.current.append_child(node)
        if tag.lower() not in VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        p: DOMNode | None = self.current
        while p is not None and p is not self.root:
            if p.tag == tag_lower:
                self.current = p.parent if p.parent is not None else self.root
                break
            p = p.parent

    def handle_data(self, data: str) -> None:
        if data:
            node = DOMNode(is_text=True, text=data)
            self.current.append_child(node)


def _is_noise_node(node: DOMNode) -> bool:
    """Checks whether a DOM node represents boilerplate noise."""
    if node.is_text:
        return False
    if node.tag in NOISE_TAGS:
        return True
    class_val = node.get_attr("class")
    if class_val and NOISE_ATTR_PATTERN.search(class_val):
        return True
    id_val = node.get_attr("id")
    if id_val and NOISE_ATTR_PATTERN.search(id_val):
        return True
    return False


def _find_nodes(root: DOMNode, predicate: Callable[[DOMNode], bool]) -> list[DOMNode]:
    """Depth-first search collecting nodes matching the given predicate."""
    results: list[DOMNode] = []

    def _walk(node: DOMNode) -> None:
        if predicate(node):
            results.append(node)
        for child in node.children:
            _walk(child)

    _walk(root)
    return results


def select_primary_container(root: DOMNode) -> DOMNode:
    """
    Selects the primary content container from a parsed DOM tree based on semantic hierarchy.
    """
    selectors: list[Callable[[DOMNode], bool]] = [
        lambda n: n.tag == "article",
        lambda n: n.tag == "main",
        lambda n: n.get_attr("role") == "main",
        lambda n: n.get_attr("id") == "mw-content-text",
        lambda n: n.has_class("mw-parser-output"),
        lambda n: n.has_class("post-content"),
        lambda n: n.has_class("article-body"),
        lambda n: n.has_class("entry-content"),
        lambda n: n.tag == "body",
    ]

    for sel in selectors:
        matches = _find_nodes(root, sel)
        if matches:
            if len(matches) == 1:
                if len(matches[0].get_text_content().strip()) > 30:
                    return matches[0]
            else:
                best = max(matches, key=lambda m: len(m.get_text_content().strip()))
                if len(best.get_text_content().strip()) > 30:
                    return best

    return root


def serialize_node(node: DOMNode) -> str:
    """Serializes a DOM node back to HTML while discarding noise subtrees."""
    if node.is_text:
        return node.text
    if _is_noise_node(node):
        return ""

    if node.tag in VOID_TAGS:
        attr_str = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
        return f"<{node.tag}{attr_str} />"

    inner_html = "".join(serialize_node(c) for c in node.children)
    if node.tag.startswith("["):
        return inner_html

    attr_str = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
    return f"<{node.tag}{attr_str}>{inner_html}</{node.tag}>"


def sanitize_html_boilerplate(html_content: str) -> str:
    """
    Sanitizes HTML content by:
    1. Parsing the HTML into a lightweight DOM tree.
    2. Isolating the primary container (<article>, <main>, #mw-content-text, etc.).
    3. Pruning noise tags, classes, and IDs.
    4. Stripping Wikipedia citations and edit markers.
    5. Normalizing punctuation spacing.

    Args:
        html_content: Raw HTML document string.

    Returns:
        Cleaned, sanitized HTML string ready for Markdown conversion.
    """
    if not html_content or not html_content.strip():
        return ""

    builder = DOMTreeBuilder()
    builder.feed(html_content)

    container = select_primary_container(builder.root)
    sanitized_html = serialize_node(container)

    cleaned_html = sanitized_html
    if "[" in cleaned_html:
        cleaned_html = WIKIPEDIA_CITATION_PATTERN.sub("", cleaned_html)

    cleaned_html = _RE_ORPHAN_PUNCTUATION_SPACE.sub(r"\1", cleaned_html)

    return cleaned_html.strip()


strip_html_boilerplate = sanitize_html_boilerplate


class HTMLToMarkdownParser(HTMLParser):
    """
    Robust, zero-dependency HTML-to-Markdown streaming converter based on html.parser.HTMLParser.
    Converts semantic HTML tags into standard Markdown representations while safely discarding
    unwanted scripts, styles, navigation bars, and footers.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []
        self._tag_stack: list[str] = []
        self._list_stack: list[dict[str, Any]] = []
        self._ignore_depth: int = 0
        self._in_pre: bool = False
        self._in_code: bool = False
        self._blockquote_depth: int = 0
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag in (
            "aside",
            "button",
            "canvas",
            "dialog",
            "footer",
            "form",
            "head",
            "header",
            "iframe",
            "nav",
            "noscript",
            "script",
            "select",
            "style",
            "svg",
            "template",
            "textarea",
        ):
            self._ignore_depth += 1
            return

        if self._ignore_depth > 0:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self._ensure_newlines(2)
            self._pieces.append("#" * level + " ")
        elif tag == "p":
            self._ensure_newlines(2)
            if self._blockquote_depth > 0:
                self._pieces.append("> ")
        elif tag == "br":
            self._ensure_newlines(1)
            if self._blockquote_depth > 0:
                self._pieces.append("> ")
        elif tag == "hr":
            self._ensure_newlines(2)
            self._pieces.append("---\n\n")
        elif tag in ("b", "strong"):
            self._pieces.append("**")
        elif tag in ("em", "i"):
            self._pieces.append("*")
        elif tag in ("del", "s", "strike"):
            self._pieces.append("~~")
        elif tag == "code":
            if not self._in_pre:
                self._in_code = True
                self._pieces.append("`")
        elif tag == "pre":
            self._in_pre = True
            self._ensure_newlines(2)
            self._pieces.append("```\n")
        elif tag == "blockquote":
            self._blockquote_depth += 1
            self._ensure_newlines(2)
            self._pieces.append("> ")
        elif tag == "ul":
            self._list_stack.append({"count": 0, "type": "ul"})
            self._ensure_newlines(1)
        elif tag == "ol":
            self._list_stack.append({"count": 0, "type": "ol"})
            self._ensure_newlines(1)
        elif tag == "li":
            self._ensure_newlines(1)
            depth = max(0, len(self._list_stack) - 1)
            indent = "  " * depth
            if self._list_stack and self._list_stack[-1]["type"] == "ol":
                current_cnt = int(self._list_stack[-1]["count"]) + 1
                self._list_stack[-1]["count"] = current_cnt
                self._pieces.append(f"{indent}{current_cnt}. ")
            else:
                self._pieces.append(f"{indent}* ")
        elif tag in ("td", "th", "tr"):
            if tag == "tr":
                self._ensure_newlines(1)
            elif tag in ("td", "th"):
                self._pieces.append(" ")
        elif tag == "a":
            href = attrs_dict.get("href", "").strip()
            if (
                href
                and not href.startswith(("javascript:", "mailto:"))
                and not href.startswith("#")
            ):
                self._link_href = href
                self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        elif tag in self._tag_stack:
            while self._tag_stack and self._tag_stack[-1] != tag:
                self._tag_stack.pop()
            if self._tag_stack:
                self._tag_stack.pop()

        if tag in (
            "aside",
            "button",
            "canvas",
            "dialog",
            "footer",
            "form",
            "head",
            "header",
            "iframe",
            "nav",
            "noscript",
            "script",
            "select",
            "style",
            "svg",
            "template",
            "textarea",
        ):
            self._ignore_depth = max(0, self._ignore_depth - 1)
            return

        if self._ignore_depth > 0:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._ensure_newlines(2)
        elif tag == "p":
            self._ensure_newlines(2)
        elif tag in ("b", "strong"):
            self._pieces.append("**")
        elif tag in ("em", "i"):
            self._pieces.append("*")
        elif tag in ("del", "s", "strike"):
            self._pieces.append("~~")
        elif tag == "code":
            if not self._in_pre and self._in_code:
                self._in_code = False
                self._pieces.append("`")
        elif tag == "pre":
            self._in_pre = False
            self._ensure_newlines(1)
            self._pieces.append("\n```\n\n")
        elif tag == "blockquote":
            self._blockquote_depth = max(0, self._blockquote_depth - 1)
            self._ensure_newlines(2)
        elif tag in ("ol", "ul"):
            if self._list_stack:
                self._list_stack.pop()
            self._ensure_newlines(1)
        elif tag in ("td", "th", "tr"):
            if tag == "tr":
                self._ensure_newlines(1)
            elif tag in ("td", "th"):
                self._pieces.append(" ")
        elif tag == "a":
            if self._link_href is not None:
                anchor_text = "".join(self._link_text).strip()
                if anchor_text:
                    self._pieces.append(f"[{anchor_text}]({self._link_href})")
                self._link_href = None
                self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        if self._link_href is not None:
            self._link_text.append(data)
            return
        if self._in_pre:
            self._pieces.append(data)
            return

        if not data:
            return

        if not data.strip():
            if self._pieces and not self._pieces[-1].endswith((" ", "\n")):
                self._pieces.append(" ")
            return

        # PERFORMANCE OPTIMIZATION: Fast-path guard to bypass regex substitution when whitespace is normal
        if "\t" in data or "\r" in data or "\n" in data or "  " in data:
            cleaned = re.sub(r"[ \t\r\n]+", " ", data)
        else:
            cleaned = data

        if (
            data.startswith((" ", "\t", "\n"))
            and self._pieces
            and not self._pieces[-1].endswith((" ", "\n"))
        ):
            cleaned = " " + cleaned.lstrip()
        if data.endswith((" ", "\t", "\n")) and not cleaned.endswith(" "):
            cleaned = cleaned.rstrip() + " "

        self._pieces.append(cleaned)

    def _ensure_newlines(self, count: int = 1) -> None:
        if not self._pieces:
            return
        while self._pieces and self._pieces[-1] == " ":
            self._pieces.pop()

        # PERFORMANCE OPTIMIZATION: Scan pieces backwards to count trailing newlines
        # in O(1) instead of re-joining the entire self._pieces list O(N^2) on every tag.
        trailing_newlines = 0
        for piece in reversed(self._pieces):
            if not piece:
                continue
            stripped = piece.rstrip("\n")
            if stripped:
                trailing_newlines += len(piece) - len(stripped)
                break
            else:
                trailing_newlines += len(piece)
            if trailing_newlines >= count:
                break

        needed = count - trailing_newlines
        if needed > 0:
            self._pieces.append("\n" * needed)

    def get_markdown(self) -> str:
        return "".join(self._pieces).strip()


def convert_html_to_markdown(html_content: str) -> str:
    """
    Converts HTML content into structured Markdown using MarkItDown if available,
    with a robust built-in HTMLToMarkdownParser fallback.

    Args:
        html_content: Raw or sanitized HTML string.

    Returns:
        Structured, normalized Markdown string.
    """
    if not html_content or not html_content.strip():
        return ""

    # Tier 1: Dynamic MarkItDown if installed
    try:
        from markitdown import MarkItDown  # type: ignore[import-not-found]

        md = MarkItDown()
        stream = io.BytesIO(html_content.encode("utf-8", errors="replace"))
        result = md.convert_stream(stream, file_extension=".html")
        if result and getattr(result, "text_content", None) and result.text_content.strip():
            return normalize_extracted_text(result.text_content)
    except (ImportError, Exception):
        pass

    # Tier 2: Built-in HTMLToMarkdownParser fallback
    try:
        parser = HTMLToMarkdownParser()
        parser.feed(html_content)
        parser.close()
        markdown = parser.get_markdown()
        if markdown and markdown.strip():
            return normalize_extracted_text(markdown)
    except Exception:
        pass

    # Tier 3: Regex tag strip fallback
    fallback_text = re.sub(r"<[^>]+>", " ", html_content)
    return normalize_extracted_text(fallback_text)


def extract_text_from_pdf(
    pdf_path: str,
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> str:
    """
    Extracts and normalizes text from a PDF document using pypdf.
    Handles encryption/password, whitespace normalization, and dehyphenation.
    Enforces maximum file size and page count bounds.

    Raises:
        DocumentExtractionError: If file not found, exceeds size/page bounds,
                                 corrupt, encrypted, or has no extractable text layer.
    """
    if not os.path.exists(pdf_path):
        raise DocumentExtractionError(f"PDF file not found: {pdf_path}")

    try:
        file_size_bytes = os.path.getsize(pdf_path)
    except OSError as e:
        raise DocumentExtractionError(
            f"Cannot access PDF file '{os.path.basename(pdf_path)}': {e}"
        ) from e

    max_size_bytes = max_file_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        size_mb = file_size_bytes / (1024 * 1024)
        raise DocumentExtractionError(
            f"PDF file '{os.path.basename(pdf_path)}' exceeds the maximum allowed size of {max_file_size_mb} MB ({size_mb:.1f} MB)."
        )

    try:
        from pypdf import PdfReader
        from pypdf import errors as pypdf_errors
    except ImportError as err:
        raise DocumentExtractionError(
            "pypdf package is not installed. Please install pypdf to extract PDF documents."
        ) from err

    try:
        reader = PdfReader(pdf_path)
    except (pypdf_errors.PdfReadError, OSError, ValueError, KeyError) as e:
        raise DocumentExtractionError(
            f"Failed to open or parse PDF file '{os.path.basename(pdf_path)}': {e}"
        ) from e

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except (pypdf_errors.PdfReadError, OSError, ValueError, KeyError) as decrypt_err:
            raise DocumentExtractionError(
                f"PDF file '{os.path.basename(pdf_path)}' is password protected and cannot be extracted."
            ) from decrypt_err

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise DocumentExtractionError(f"PDF file '{os.path.basename(pdf_path)}' contains 0 pages.")

    if total_pages > max_pages:
        raise DocumentExtractionError(
            f"PDF file '{os.path.basename(pdf_path)}' exceeds the maximum allowed limit of {max_pages} pages ({total_pages} pages found). "
            "Please split the document or select a shorter excerpt."
        )

    page_texts = []
    for _idx, page in enumerate(reader.pages):
        try:
            page_content = page.extract_text()
            if page_content and page_content.strip():
                page_texts.append(page_content.strip())
        except (ValueError, KeyError, TypeError, OSError):
            continue

    if not page_texts:
        raise DocumentExtractionError(
            f"The selected PDF '{os.path.basename(pdf_path)}' contains no extractable text. "
            "It may be a scanned image or encrypted document. "
            "Please provide a text-based document or paste text directly."
        )

    combined_text = "\n\n".join(page_texts)
    return normalize_extracted_text(combined_text)


def extract_text_from_file(
    file_path: str,
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> str:
    """
    Extracts text from .txt, .md, or .pdf files with multi-encoding fallback.
    Supported encodings: UTF-8-BOM, UTF-8, CP1252, Latin-1, ISO-8859-1.
    Enforces maximum file size and PDF page count limits.

    Raises:
        DocumentExtractionError: If file not found, exceeds size limits,
                                 unsupported format, or extraction fails.
    """
    if not os.path.exists(file_path):
        raise DocumentExtractionError(f"File not found: {file_path}")

    try:
        file_size_bytes = os.path.getsize(file_path)
    except OSError as e:
        raise DocumentExtractionError(
            f"Cannot access file '{os.path.basename(file_path)}': {e}"
        ) from e

    max_size_bytes = max_file_size_mb * 1024 * 1024
    if file_size_bytes > max_size_bytes:
        size_mb = file_size_bytes / (1024 * 1024)
        raise DocumentExtractionError(
            f"File '{os.path.basename(file_path)}' exceeds the maximum allowed size of {max_file_size_mb} MB ({size_mb:.1f} MB)."
        )

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(
            file_path, max_file_size_mb=max_file_size_mb, max_pages=max_pages
        )

    if ext in [".txt", ".md", ".markdown", ".rst", ".text", ".log", ".json", ".csv"]:
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
        content = None
        for enc in encodings:
            try:
                with open(file_path, encoding=enc) as f:
                    data = f.read()
                    if data is not None:
                        content = data
                        break
            except (UnicodeDecodeError, LookupError):
                continue
            except OSError as e:
                raise DocumentExtractionError(
                    f"Error reading file '{os.path.basename(file_path)}': {e}"
                ) from e

        if content is None:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError as e:
                raise DocumentExtractionError(
                    f"Failed to read file '{os.path.basename(file_path)}': {e}"
                ) from e

        normalized = normalize_extracted_text(content)
        if not normalized or len(normalized.strip()) < 5:
            raise DocumentExtractionError(
                f"File '{os.path.basename(file_path)}' is empty or contains insufficient content."
            )
        return normalized

    raise DocumentExtractionError(
        f"Unsupported file format '{ext}'. LocalPodcastLLMStudio supports .txt, .md, and .pdf documents."
    )


def extract_text_from_url(
    url: str,
    timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    max_size_bytes: int = DEFAULT_MAX_URL_SIZE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Extracts, cleans, and converts web page content from a URL into normalized Markdown.
    Chains SSRF validation -> Streaming safe fetch -> DOM boilerplate removal -> Markdown conversion.

    Args:
        url: Target HTTP/HTTPS URL.
        timeout: Maximum network timeout in seconds (default: 10.0).
        max_size_bytes: Maximum downloaded content size in bytes (default: 5 MB).
        max_redirects: Maximum allowed redirect hops (default: 5).
        progress_callback: Optional progress message callback function.

    Returns:
        Clean, structured Markdown text.

    Raises:
        SecurityError: If URL or any redirect hop fails SSRF/protocol security checks.
        DocumentExtractionError: If network request fails, exceeds bounds, or content is empty.
    """
    if progress_callback:
        progress_callback(f"Validating target URL: {url}")
    validated_url = validate_url_target(url)

    if progress_callback:
        progress_callback(f"Fetching web page: {validated_url}")
    raw_html = fetch_url_content(
        validated_url,
        timeout=timeout,
        max_size_bytes=max_size_bytes,
        max_redirects=max_redirects,
        progress_callback=progress_callback,
    )

    if progress_callback:
        progress_callback("Sanitizing HTML and removing noise elements...")
    sanitized_html = sanitize_html_boilerplate(raw_html)

    if progress_callback:
        progress_callback("Converting sanitized content to Markdown...")
    markdown_text = convert_html_to_markdown(sanitized_html)

    if not markdown_text or len(markdown_text.strip()) < 5:
        raise DocumentExtractionError(
            f"Web page at '{url}' contains insufficient extractable text content."
        )

    return markdown_text


def extract_text(
    source: str | os.PathLike[Any],
    is_raw_text: bool = False,
    is_topic: bool = False,
    is_url: bool = False,
    timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    max_size_bytes: int = DEFAULT_MAX_URL_SIZE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    """
    Unified extraction entry point supporting URLs, files (.txt, .md, .pdf), pasted text, and scratch topic prompts.
    Auto-detects HTTP/HTTPS URLs even when is_url is not explicitly passed.

    Args:
        source: File path, URL, raw text, or topic prompt string.
        is_raw_text: True if source is directly pasted raw text.
        is_topic: True if source is a topic/prompt for 'Generate from Scratch' mode.
        is_url: True if source is explicitly marked as a URL.
        timeout: Maximum network timeout in seconds for URLs.
        max_size_bytes: Maximum allowed downloaded content size in bytes for URLs.
        max_redirects: Maximum allowed redirect hops for URLs.
        max_file_size_mb: Maximum allowed file size in MB (default: 50).
        max_pages: Maximum allowed PDF page count (default: 200).
        progress_callback: Optional status callback function for UI/CLI updates.

    Returns:
        Cleaned, normalized UTF-8 string.

    Raises:
        SecurityError: If URL safety validation fails.
        DocumentExtractionError: On empty or invalid input, oversized files, or missing file.
    """
    if source is None or not isinstance(source, (str, os.PathLike)):
        raise DocumentExtractionError("Input source must be a non-empty string or path.")

    cleaned_source = str(source).strip()
    if not cleaned_source:
        raise DocumentExtractionError(
            "Input source is empty. Please provide a document, URL, text, or topic."
        )

    # 1. Topic Mode
    if is_topic:
        if len(cleaned_source) < 3:
            raise DocumentExtractionError(
                "Topic prompt is too short. Please provide a descriptive topic or question."
            )
        return normalize_extracted_text(cleaned_source)

    # 2. Raw Pasted Text Mode
    if is_raw_text:
        normalized = normalize_extracted_text(cleaned_source)
        if len(normalized) < 5:
            raise DocumentExtractionError(
                "Pasted text is too short. Please provide at least a few words."
            )
        return normalized

    # 3. URL Ingestion Mode (Explicit flag or auto-detection)
    if is_url or cleaned_source.lower().startswith(("http://", "https://")):
        return extract_text_from_url(
            cleaned_source,
            timeout=timeout,
            max_size_bytes=max_size_bytes,
            max_redirects=max_redirects,
            progress_callback=progress_callback,
        )

    # 4. File Path Mode (Existing file on disk)
    if os.path.exists(cleaned_source):
        return extract_text_from_file(
            cleaned_source,
            max_file_size_mb=max_file_size_mb,
            max_pages=max_pages,
        )

    # 5. Missing File Detection
    if (
        any(
            cleaned_source.lower().endswith(ext)
            for ext in [".txt", ".md", ".pdf", ".png", ".jpg", ".doc", ".docx", ".epub"]
        )
        or (("/" in cleaned_source or "\\" in cleaned_source) and len(cleaned_source) < 300)
        or (len(cleaned_source) < 100 and " " not in cleaned_source)
    ):
        raise DocumentExtractionError(f"Specified document file not found: {cleaned_source}")

    # 6. Fallback to Raw Text
    normalized = normalize_extracted_text(cleaned_source)
    if len(normalized) < 5:
        raise DocumentExtractionError(
            "Provided text is too short. Please provide at least a few words."
        )
    return normalized
