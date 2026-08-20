"""
LocalPodcastLLMStudio - Zero-FFmpeg MP3 Binary Frame Stitcher
100% pure Python MPEG Audio Layer III frame extractor, ID3v2 tag stripper,
inter-speaker silence frame injector, and unified ID3v2.3 metadata writer.
Zero external ffmpeg binary dependencies.
"""

import io
import os
import struct
from collections.abc import Sequence


class MP3Stitcher:
    """
    Pure Python MP3 Binary Frame Stitcher.
    Extracts pure MPEG-1/2 Audio Layer III frames, strips ID3 headers,
    aligns audio sync words, injects silent frames between speaker turns,
    and prepends a valid ID3v2.3 metadata header.
    """

    # MPEG Sampling Rates (Hz): [version_id][sampling_rate_index]
    # Version ID: 3=MPEG-1, 2=MPEG-2 (ISO/IEC 13818-3), 0=MPEG-2.5
    SAMPLING_RATES = {
        3: [44100, 48000, 32000],
        2: [22050, 24000, 16000],
        0: [11025, 12000, 8000],
    }

    # MPEG Layer III Bitrate Tables (kbps) indexed by bitrate_index (0..15)
    MPEG1_L3_BITRATES = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    MPEG2_L3_BITRATES = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]

    # Samples per frame: 1152 for MPEG-1 Layer III, 576 for MPEG-2/2.5 Layer III
    SAMPLES_PER_FRAME = {
        3: 1152,
        2: 576,
        0: 576,
    }

    @classmethod
    def strip_id3(cls, mp3_data: bytes) -> bytes:
        """
        Strips ID3v2 metadata header from the beginning and ID3v1 from the end of MP3 data.
        """
        if not mp3_data:
            return b""

        pos = 0
        total_len = len(mp3_data)

        # 1. Strip ID3v2 Header(s) at start
        while pos + 10 <= total_len and mp3_data[pos : pos + 3] == b"ID3":
            flags = mp3_data[pos + 5]
            has_footer = bool(flags & 0x10)  # Bit 4 in ID3v2.4

            # Synchsafe integer size in bytes 6..9 (7 bits per byte)
            b0 = mp3_data[pos + 6] & 0x7F
            b1 = mp3_data[pos + 7] & 0x7F
            b2 = mp3_data[pos + 8] & 0x7F
            b3 = mp3_data[pos + 9] & 0x7F
            tag_size = (b0 << 21) | (b1 << 14) | (b2 << 7) | b3

            header_total = 10 + tag_size + (10 if has_footer else 0)
            pos += header_total

        end_pos = total_len

        # 2. Strip trailing ID3v1 Tag (128 bytes starting with 'TAG')
        if end_pos - pos >= 128 and mp3_data[end_pos - 128 : end_pos - 125] == b"TAG":
            end_pos -= 128

        # 3. Strip trailing Enhanced ID3v1 Tag ('TAG+' 227 bytes)
        if end_pos - pos >= 227 and mp3_data[end_pos - 227 : end_pos - 223] == b"TAG+":
            end_pos -= 227

        if pos >= end_pos:
            return b""

        return mp3_data[pos:end_pos]

    @classmethod
    def parse_frame_header(cls, header_bytes: bytes) -> tuple[int, int, int, int] | None:
        """
        Parses a 4-byte MPEG Audio header.

        Returns:
            (frame_length_bytes, version_id, bitrate_kbps, sample_rate_hz)
            or None if header is invalid or not Layer III.
        """
        if len(header_bytes) < 4:
            return None

        b0, b1, b2, _b3 = header_bytes[0], header_bytes[1], header_bytes[2], header_bytes[3]

        # Check sync word (11 bits = 0xFF followed by 0xE0 mask in byte 1)
        if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
            return None

        version_id = (b1 >> 3) & 0x03  # 3=MPEG-1, 2=MPEG-2, 0=MPEG-2.5, 1=reserved
        layer = (b1 >> 1) & 0x03  # 1=Layer III, 2=Layer II, 3=Layer I, 0=reserved

        if version_id == 1 or layer != 1:
            return None

        bitrate_idx = (b2 >> 4) & 0x0F
        sr_idx = (b2 >> 2) & 0x03
        padding = (b2 >> 1) & 0x01

        if bitrate_idx == 0 or bitrate_idx == 15 or sr_idx == 3:
            return None

        version_key = version_id if version_id in (3, 2, 0) else 2
        sample_rates = cls.SAMPLING_RATES.get(version_key, [24000, 24000, 24000])
        sample_rate = sample_rates[sr_idx]

        if version_id == 3:
            bitrate = cls.MPEG1_L3_BITRATES[bitrate_idx]
            frame_len = int((144 * bitrate * 1000) / sample_rate) + padding
        else:
            bitrate = cls.MPEG2_L3_BITRATES[bitrate_idx]
            frame_len = int((72 * bitrate * 1000) / sample_rate) + padding

        if frame_len < 4 or frame_len > 4000:
            return None

        return frame_len, version_id, bitrate, sample_rate

    @classmethod
    def extract_audio_frames(cls, mp3_data: bytes) -> bytes:
        """
        Scans binary MP3 data, strips ID3 tags, and extracts contiguous valid MPEG Layer III frames.

        Returns:
            Pure MPEG audio frames as bytes.
        """
        clean_data = cls.strip_id3(mp3_data)
        if not clean_data:
            return b""

        out = io.BytesIO()
        idx = 0
        total_len = len(clean_data)

        while idx <= total_len - 4:
            if clean_data[idx] == 0xFF and (clean_data[idx + 1] & 0xE0) == 0xE0:
                header_info = cls.parse_frame_header(clean_data[idx : idx + 4])
                if header_info:
                    frame_len, _, _, _ = header_info
                    if idx + frame_len <= total_len:
                        out.write(clean_data[idx : idx + frame_len])
                        idx += frame_len
                        continue
            idx += 1

        return out.getvalue()

    @classmethod
    def generate_silence_frame(
        cls,
        version_id: int = 2,
        bitrate_kbps: int = 48,
        sample_rate: int = 24000,
        channel_mode: int = 3,
    ) -> bytes:
        """
        Generates a valid, standard-compliant MPEG Layer III silent frame.
        For Edge-TTS (MPEG-2 Layer III 24kHz, 48kbps, mono), frame length is exactly 144 bytes.
        """
        sr_rates = cls.SAMPLING_RATES.get(version_id, [24000, 24000, 24000])
        sr_idx = 1
        for idx, sr in enumerate(sr_rates):
            if sr == sample_rate:
                sr_idx = idx
                break

        bitrates = cls.MPEG1_L3_BITRATES if version_id == 3 else cls.MPEG2_L3_BITRATES
        bitrate_idx = 4  # Default 48kbps
        for idx, br in enumerate(bitrates):
            if br == bitrate_kbps:
                bitrate_idx = idx
                break

        b1 = 0xE0 | ((version_id & 0x03) << 3) | (0x01 << 1) | 0x01
        b2 = ((bitrate_idx & 0x0F) << 4) | ((sr_idx & 0x03) << 2)
        b3 = (channel_mode & 0x03) << 6

        header = bytes([0xFF, b1, b2, b3])

        if version_id == 3:
            frame_len = int((144 * bitrate_kbps * 1000) / sample_rate)
        else:
            frame_len = int((72 * bitrate_kbps * 1000) / sample_rate)

        payload_len = max(0, frame_len - 4)
        payload = bytes(payload_len)

        return header + payload

    @classmethod
    def generate_silence_bytes(
        cls,
        duration_ms: int = 350,
        version_id: int = 2,
        bitrate_kbps: int = 48,
        sample_rate: int = 24000,
        channel_mode: int = 3,
    ) -> bytes:
        """
        Generates silence MPEG audio frames corresponding to the desired duration in ms.
        """
        if duration_ms <= 0:
            return b""

        samples_per_frame = cls.SAMPLES_PER_FRAME.get(version_id, 576)
        frame_duration_ms = (samples_per_frame / sample_rate) * 1000.0
        num_frames = max(1, int(round(duration_ms / frame_duration_ms)))

        single_frame = cls.generate_silence_frame(
            version_id=version_id,
            bitrate_kbps=bitrate_kbps,
            sample_rate=sample_rate,
            channel_mode=channel_mode,
        )

        return single_frame * num_frames

    @classmethod
    def build_id3v23_tag(
        cls,
        title: str = "Podcast Episode",
        artist: str = "LocalPodcastLLMStudio",
        album: str = "LocalPodcastLLMStudio AI Podcast",
        year: str = "2026",
        genre: str = "Podcast",
    ) -> bytes:
        """
        Builds a standard ID3v2.3 metadata header with UTF-16 / ISO-8859-1 frames.
        """
        frames_buf = io.BytesIO()

        def write_frame(frame_id: str, text: str) -> None:
            if not text:
                return
            encoded_text = text.encode("utf-16")
            frame_data = b"\x01" + encoded_text
            frame_len = len(frame_data)
            frames_buf.write(frame_id.encode("ascii")[:4])
            frames_buf.write(struct.pack(">I", frame_len))
            frames_buf.write(b"\x00\x00")  # Flags (2 bytes)
            frames_buf.write(frame_data)

        write_frame("TIT2", title)
        write_frame("TPE1", artist)
        write_frame("TALB", album)
        write_frame("TYER", year)
        write_frame("TCON", genre)

        frames_bytes = frames_buf.getvalue()
        tag_size = len(frames_bytes)

        # Convert size to 28-bit synchsafe integer (7 bits per byte)
        b0 = (tag_size >> 21) & 0x7F
        b1 = (tag_size >> 14) & 0x7F
        b2 = (tag_size >> 7) & 0x7F
        b3 = tag_size & 0x7F

        header = b"ID3\x03\x00\x00" + bytes([b0, b1, b2, b3])
        return header + frames_bytes

    @classmethod
    def stitch(
        cls,
        segments: Sequence[bytes | bytearray],
        title: str = "Podcast Episode",
        artist: str = "LocalPodcastLLMStudio",
        album: str = "LocalPodcastLLMStudio AI Podcast",
        pause_ms: int = 350,
    ) -> bytes:
        """
        Stitches a list of MP3 byte segments in-memory into a single MP3 byte buffer.
        """
        if not segments:
            return b""

        extracted_frames: list[bytes] = []
        stream_info: tuple[int, int, int, int] | None = None

        for seg in segments:
            raw_data = bytes(seg)
            if not raw_data:
                continue
            pure_frames = cls.extract_audio_frames(raw_data)
            if pure_frames:
                extracted_frames.append(pure_frames)
                if stream_info is None and len(pure_frames) >= 4:
                    stream_info = cls.parse_frame_header(pure_frames[:4])

        if not extracted_frames:
            return b""

        if stream_info is not None:
            _, version_id, bitrate_kbps, sample_rate = stream_info
        else:
            version_id = 2
            bitrate_kbps = 48
            sample_rate = 24000

        silence_bytes = cls.generate_silence_bytes(
            duration_ms=pause_ms,
            version_id=version_id,
            bitrate_kbps=bitrate_kbps,
            sample_rate=sample_rate,
            channel_mode=3,
        )

        out = io.BytesIO()
        id3_tag = cls.build_id3v23_tag(title=title, artist=artist, album=album)
        out.write(id3_tag)

        for idx, turn_bytes in enumerate(extracted_frames):
            if idx > 0 and silence_bytes:
                out.write(silence_bytes)
            out.write(turn_bytes)

        return out.getvalue()


def stitch_mp3_files(
    input_files_or_bytes: Sequence[str | bytes | bytearray],
    output_file_path: str,
    silence_duration_ms: int = 350,
    title: str = "Podcast Episode",
    artist: str = "LocalPodcastLLMStudio",
    album: str = "LocalPodcastLLMStudio AI Podcast",
) -> str:
    """
    Stitches multiple MP3 audio files or byte buffers into a single master MP3 file.

    Returns:
        Absolute path to the created master MP3 file.
    """
    if not input_files_or_bytes:
        raise ValueError("Cannot stitch empty list of MP3 inputs.")

    byte_segments: list[bytes] = []
    for item in input_files_or_bytes:
        if isinstance(item, str):
            if not os.path.exists(item):
                continue
            with open(item, "rb") as f:
                byte_segments.append(f.read())
        elif isinstance(item, (bytes, bytearray)):
            byte_segments.append(bytes(item))

    stitched_bytes = MP3Stitcher.stitch(
        segments=byte_segments,
        title=title,
        artist=artist,
        album=album,
        pause_ms=silence_duration_ms,
    )

    if not stitched_bytes:
        raise ValueError("No valid MPEG Layer III audio frames could be extracted from inputs.")

    abs_out_path = os.path.abspath(output_file_path)
    os.makedirs(os.path.dirname(abs_out_path), exist_ok=True)

    with open(abs_out_path, "wb") as f:
        f.write(stitched_bytes)

    return abs_out_path
