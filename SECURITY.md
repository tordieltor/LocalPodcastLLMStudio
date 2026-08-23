# Security Policy — LocalPodcastLLMStudio

**LocalPodcastLLMStudio** is designed from the ground up as a **100% local, air-gapped, privacy-first desktop application**.
All document processing, LLM dialogue generation, neural voice synthesis (Piper TTS), and audio assembly operate locally on your machine with zero data transmitted to the cloud or third parties.

---

## 1. Supported Versions

We actively maintain and provide security patches for the following versions of LocalPodcastLLMStudio:

| Version | Supported          | Status                                 |
| ------- | ------------------ | -------------------------------------- |
| 0.7.x   | :white_check_mark: | Current release (Active support)       |
| main    | :white_check_mark: | Development branch (Bleeding edge)     |
| < 0.7.0 | :x:                | Legacy / Unsupported                   |

If you are running an unsupported version, please upgrade to the latest release before submitting a vulnerability report.

---

## 2. Reporting a Vulnerability

We take the security and privacy of LocalPodcastLLMStudio seriously. If you believe you have discovered a security vulnerability, please report it responsibly following the guidelines below.

### Primary Disclosure Method (Preferred)
Please use **[GitHub Private Vulnerability Reporting](https://github.com/tordieltor/LocalPodcastLLMStudio/security/advisories/new)**:
1. Navigate to the **Security** tab of the repository.
2. Click on **Advisories** -> **Report a vulnerability**.
3. Fill out the advisory form with detailed reproduction steps and impact analysis.

### Secondary Contact
If you are unable to use GitHub Private Vulnerability Reporting, contact the maintainers directly:
- **Security Contact**: `security@localpodcastllmstudio.dev`

### Information to Include
To help us triage and resolve the issue quickly, please include:
- Description and classification of the vulnerability (e.g., SSRF, DoS, Path Traversal).
- Affected version or commit hash.
- Step-by-step instructions to reproduce the issue (proof-of-concept scripts, sample files, or payloads).
- Potential impact and threat model (e.g., local privilege escalation, arbitrary file read).
- Any proposed remediation or patch if available.

### Response SLA & Timeline
- **Initial Acknowledgment**: Within **48 hours** of report receipt.
- **Triage & Validation**: Within **5 business days**, confirming severity and scope.
- **Remediation & Patch Release**: Within **14 business days** for high/critical vulnerabilities.
- **Public Advisory Disclosure**: Coordinated after the fix has been tagged and released.

---

## 3. Safe Harbor & Responsible Disclosure

We support and appreciate good-faith security research:
- We will **not** pursue legal action against researchers who report vulnerabilities in good faith and follow responsible disclosure practices.
- Please give the project maintainers reasonable time to remediate issues before making details public.
- Do not attempt to access, alter, or destroy user data during testing.

---

## 4. Privacy & Threat Model Architecture

LocalPodcastLLMStudio incorporates defense-in-depth security principles:

1. **100% Local Inference & Offline Voice Synthesis**:
   - Dialogue generation is executed against locally hosted Ollama instances (`http://127.0.0.1:11434`).
   - Source documents, prompt templates, and generated transcripts are processed strictly in local workstation memory and are never transmitted to third-party cloud LLM APIs.
   - Voice synthesis runs 100% offline via local Piper ONNX neural voice models. Zero dialogue text or audio data is ever transmitted to Microsoft, Bing, or any cloud endpoints.

2. **Strict URL Scheme Validation**:
   - All network connections to the Ollama REST API strictly enforce `http://` or `https://` schemes and valid hostnames, mitigating Server-Side Request Forgery (SSRF) and local file access (`file://`) vectors.

3. **Input Bounds & Denial-of-Service (DoS) Protection**:
   - Ingestion bounds are enforced on all imported documents (max **50 MB** file size and max **200 pages** for PDF documents).
   - Safe dehyphenation and multi-encoding fallbacks (`utf-8-sig`, `utf-8`, `cp1252`, `latin-1`, `iso-8859-1`) prevent parser crashes on corrupted byte sequences.

4. **100% Local Storage & Ephemeral Lifecycle**:
   - Audio segments are generated in isolated temporary folders (`tempfile.mkdtemp`) and are deterministically deleted upon stitching completion. Zero telemetry, tracking, or cloud sync.

5. **Safe Process Execution**:
   - Zero invocation of `subprocess` with `shell=True`.
   - Windows native audio playback utilizes the Windows Multimedia API (`winmm.dll` MCI) via `ctypes` with strict resource handle disposal.

---

## 5. Local Hardening Best Practices

When deploying LocalPodcastLLMStudio in production or multi-user environments:
- **Bind Ollama Locally**: Ensure Ollama is configured to listen only on `127.0.0.1:11434` (`OLLAMA_HOST=127.0.0.1:11434`). Do not expose the Ollama port to public interfaces without authentication.
- **Verify Release Checksums**: Always verify SHA-256 checksums of downloaded `LocalPodcastLLMStudio.exe` binaries against official GitHub Release signatures.
