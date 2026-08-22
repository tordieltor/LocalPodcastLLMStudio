"""
LocalPodcastLLMStudio - Document Ingestion & Text Extraction Engine
Supports .txt, .md, .pdf files, pasted raw text, and scratch topic prompts.
"""

import os
import re
from typing import Any

from core.exceptions import DocumentExtractionError

# Safe document ingestion bounds to protect against memory exhaustion (DoS)
DEFAULT_MAX_FILE_SIZE_MB: int = 50
DEFAULT_MAX_FILE_SIZE_BYTES: int = DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024  # 52,428,800 bytes
DEFAULT_MAX_PDF_PAGES: int = 200


# Precompiled regular expressions for text normalization performance
_RE_HYPHEN_BREAK = re.compile(r"(\b\w+)-\n(\w+\b)")
_RE_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_RE_LINE_WHITESPACE = re.compile(r" ?\n ?")
_RE_CONSECUTIVE_NEWLINES = re.compile(r"\n{3,}")


def normalize_extracted_text(raw_text: str) -> str:
    """
    Cleans and normalizes extracted text:
    1. Reconnects hyphenated line-breaks (e.g. 'auto-\\nmatic' -> 'automatic').
    2. Normalizes line endings to '\\n'.
    3. Normalizes non-breaking and Unicode spaces to standard ASCII spaces.
    4. Cleans horizontal whitespace.
    5. Collapses 3+ consecutive newlines to 2.
    """
    if not raw_text:
        return ""

    # Rejoin hyphenated line-breaks
    text = _RE_HYPHEN_BREAK.sub(r"\1\2", raw_text)

    # Normalize line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace non-breaking space and other unicode space separators
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    # Clean multiple horizontal spaces and tabs while preserving newlines
    text = _RE_HORIZONTAL_WHITESPACE.sub(" ", text)
    text = _RE_LINE_WHITESPACE.sub("\n", text)

    # Collapse excessive newlines
    text = _RE_CONSECUTIVE_NEWLINES.sub("\n\n", text)

    return text.strip()


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

    # Enforce file size limit
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

    # Check for encryption
    if reader.is_encrypted:
        try:
            # Attempt blank password decryption (standard for view-only encrypted PDFs)
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
            # Continue to next page if one page fails
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

    # Enforce file size limit
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


def extract_text(
    source: str | os.PathLike[Any],
    is_raw_text: bool = False,
    is_topic: bool = False,
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> str:
    """
    Unified extraction entry point.
    Supports file paths (.txt, .md, .pdf), direct pasted raw text, or topic prompt.

    Args:
        source: File path, raw text, or topic prompt string.
        is_raw_text: True if source is directly pasted raw text.
        is_topic: True if source is a topic/prompt for 'Generate from Scratch' mode.
        max_file_size_mb: Maximum allowed file size in MB (default: 50).
        max_pages: Maximum allowed PDF page count (default: 200).

    Returns:
        Cleaned, normalized UTF-8 string.

    Raises:
        DocumentExtractionError: On empty or invalid input, oversized files, or missing file.
    """
    if source is None or not isinstance(source, (str, os.PathLike)):
        raise DocumentExtractionError("Input source must be a non-empty string or path.")

    cleaned_source = str(source).strip()
    if not cleaned_source:
        raise DocumentExtractionError(
            "Input source is empty. Please provide a document, text, or topic."
        )

    if is_topic:
        if len(cleaned_source) < 3:
            raise DocumentExtractionError(
                "Topic prompt is too short. Please provide a descriptive topic or question."
            )
        return normalize_extracted_text(cleaned_source)

    if is_raw_text:
        normalized = normalize_extracted_text(cleaned_source)
        if len(normalized) < 5:
            raise DocumentExtractionError(
                "Pasted text is too short. Please provide at least a few words."
            )
        return normalized

    # Check if source is an existing file path
    if os.path.exists(cleaned_source):
        return extract_text_from_file(
            cleaned_source,
            max_file_size_mb=max_file_size_mb,
            max_pages=max_pages,
        )

    # If it looks like a file path or extension but file doesn't exist, raise error
    if (
        any(
            cleaned_source.lower().endswith(ext)
            for ext in [".txt", ".md", ".pdf", ".png", ".jpg", ".doc", ".docx", ".epub"]
        )
        or (("/" in cleaned_source or "\\" in cleaned_source) and len(cleaned_source) < 300)
        or (len(cleaned_source) < 100 and " " not in cleaned_source)
    ):
        raise DocumentExtractionError(f"Specified document file not found: {cleaned_source}")

    # Otherwise, treat as direct raw text
    normalized = normalize_extracted_text(cleaned_source)
    if len(normalized) < 5:
        raise DocumentExtractionError(
            "Provided text is too short. Please provide at least a few words."
        )
    return normalized
