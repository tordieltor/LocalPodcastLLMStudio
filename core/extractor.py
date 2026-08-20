"""
PodcastStudio - Document Ingestion & Text Extraction Engine
Supports .txt, .md, .pdf files, pasted raw text, and scratch topic prompts.
"""

import os
import re
from typing import Optional


class DocumentExtractionError(ValueError, FileNotFoundError):
    """Raised when text extraction from a file, document, or prompt fails."""
    pass


def normalize_extracted_text(raw_text: str) -> str:
    """
    Cleans and normalizes extracted text:
    1. Reconnects hyphenated line-breaks (e.g. 'auto-\nmatic' -> 'automatic').
    2. Normalizes line endings to '\\n'.
    3. Normalizes non-breaking and Unicode spaces to standard ASCII spaces.
    4. Cleans horizontal whitespace.
    5. Collapses 3+ consecutive newlines to 2.
    """
    if not raw_text:
        return ""

    # Rejoin hyphenated line-breaks
    text = re.sub(r"(\b\w+)-\n(\w+\b)", r"\1\2", raw_text)

    # Normalize line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace non-breaking space and other unicode space separators
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    # Clean multiple horizontal spaces and tabs while preserving newlines
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts and normalizes text from a PDF document using pypdf.
    Handles encryption/password, whitespace normalization, and dehyphenation.
    
    Raises:
        DocumentExtractionError: If file not found, corrupt, encrypted, or has no extractable text layer.
    """
    if not os.path.exists(pdf_path):
        raise DocumentExtractionError(f"PDF file not found: {pdf_path}")

    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise DocumentExtractionError(
                "pypdf package is not installed. Please install pypdf to extract PDF documents."
            )

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        raise DocumentExtractionError(f"Failed to open or parse PDF file '{os.path.basename(pdf_path)}': {e}")

    # Check for encryption
    if reader.is_encrypted:
        try:
            # Attempt blank password decryption (standard for view-only encrypted PDFs)
            reader.decrypt("")
        except Exception:
            raise DocumentExtractionError(
                f"PDF file '{os.path.basename(pdf_path)}' is password protected and cannot be extracted."
            )

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise DocumentExtractionError(f"PDF file '{os.path.basename(pdf_path)}' contains 0 pages.")

    page_texts = []
    for idx, page in enumerate(reader.pages):
        try:
            page_content = page.extract_text()
            if page_content and page_content.strip():
                page_texts.append(page_content.strip())
        except Exception:
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


def extract_text_from_file(file_path: str) -> str:
    """
    Extracts text from .txt, .md, or .pdf files with multi-encoding fallback.
    Supported encodings: UTF-8-BOM, UTF-8, CP1252, Latin-1, ISO-8859-1.
    
    Raises:
        DocumentExtractionError: If file not found, unsupported format, or extraction fails.
    """
    if not os.path.exists(file_path):
        raise DocumentExtractionError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)

    if ext in [".txt", ".md", ".markdown", ".rst", ".text", ".log", ".json", ".csv"]:
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
        content = None
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    data = f.read()
                    if data is not None:
                        content = data
                        break
            except (UnicodeDecodeError, LookupError):
                continue
            except Exception as e:
                raise DocumentExtractionError(f"Error reading file '{os.path.basename(file_path)}': {e}")

        if content is None:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                raise DocumentExtractionError(f"Failed to read file '{os.path.basename(file_path)}': {e}")

        normalized = normalize_extracted_text(content)
        if not normalized or len(normalized.strip()) < 5:
            raise DocumentExtractionError(
                f"File '{os.path.basename(file_path)}' is empty or contains insufficient content."
            )
        return normalized

    raise DocumentExtractionError(
        f"Unsupported file format '{ext}'. PodcastStudio supports .txt, .md, and .pdf documents."
    )


def extract_text(
    source: str,
    is_raw_text: bool = False,
    is_topic: bool = False
) -> str:
    """
    Unified extraction entry point.
    Supports file paths (.txt, .md, .pdf), direct pasted raw text, or topic prompt.
    
    Args:
        source: File path, raw text, or topic prompt string.
        is_raw_text: True if source is directly pasted raw text.
        is_topic: True if source is a topic/prompt for 'Generate from Scratch' mode.
        
    Returns:
        Cleaned, normalized UTF-8 string.
        
    Raises:
        DocumentExtractionError: On empty or invalid input or missing file.
    """
    if source is None or not isinstance(source, str):
        raise DocumentExtractionError("Input source must be a non-empty string.")

    cleaned_source = source.strip()
    if not cleaned_source:
        raise DocumentExtractionError("Input source is empty. Please provide a document, text, or topic.")

    if is_topic:
        if len(cleaned_source) < 3:
            raise DocumentExtractionError("Topic prompt is too short. Please provide a descriptive topic or question.")
        return normalize_extracted_text(cleaned_source)

    if is_raw_text:
        normalized = normalize_extracted_text(cleaned_source)
        if len(normalized) < 5:
            raise DocumentExtractionError("Pasted text is too short. Please provide at least a few words.")
        return normalized

    # Check if source is an existing file path
    if os.path.exists(cleaned_source):
        return extract_text_from_file(cleaned_source)

    # If it looks like a file path or extension but file doesn't exist, raise error
    if any(cleaned_source.lower().endswith(ext) for ext in [".txt", ".md", ".pdf", ".png", ".jpg", ".doc", ".docx", ".epub"]) or (
        ("/" in cleaned_source or "\\" in cleaned_source) and len(cleaned_source) < 300
    ) or (len(cleaned_source) < 100 and not " " in cleaned_source):
        raise DocumentExtractionError(f"Specified document file not found: {cleaned_source}")

    # Otherwise, treat as direct raw text
    normalized = normalize_extracted_text(cleaned_source)
    if len(normalized) < 5:
        raise DocumentExtractionError("Provided text is too short. Please provide at least a few words.")
    return normalized
