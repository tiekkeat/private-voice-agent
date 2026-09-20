from __future__ import annotations

import re
from dataclasses import dataclass


_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_HAN_RUN_PATTERN = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+)")
_LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{3}")
_WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_MALAY_MARKERS = {
    "ada",
    "akan",
    "aku",
    "awak",
    "balik",
    "belum",
    "boleh",
    "dan",
    "dengan",
    "ini",
    "itu",
    "juga",
    "kalau",
    "kamu",
    "kasih",
    "kerja",
    "lah",
    "makan",
    "macam",
    "mahu",
    "memang",
    "minum",
    "nak",
    "nanti",
    "sana",
    "saya",
    "sebab",
    "sekarang",
    "selamat",
    "sini",
    "sudah",
    "tak",
    "terima",
    "tidak",
    "untuk",
    "yang",
}


@dataclass(frozen=True)
class TTSSegment:
    language: str
    text: str


def contains_han(text: str) -> bool:
    """Return whether text contains a CJK unified ideograph."""
    return bool(_HAN_PATTERN.search(text))


def contains_latin_word(text: str) -> bool:
    """Return whether enough Latin text is present to select an English voice."""
    return bool(_LATIN_WORD_PATTERN.search(text))


def detect_latin_language(text: str) -> str:
    """Classify a Latin-script span as conversational Malay or English."""
    words = {match.group(0).lower() for match in _WORD_PATTERN.finditer(text)}
    return "ms" if words & _MALAY_MARKERS else "en"


def split_tts_segments(text: str) -> list[TTSSegment]:
    """Split mixed English/Malay/Mandarin text into speakable language spans."""
    segments: list[TTSSegment] = []
    for part in _HAN_RUN_PATTERN.split(text):
        if not part:
            continue
        if contains_han(part):
            language = "zh"
        elif not _WORD_PATTERN.search(part):
            if segments:
                previous = segments[-1]
                segments[-1] = TTSSegment(previous.language, previous.text + part)
                continue
            language = "en"
        else:
            language = detect_latin_language(part)

        if segments and segments[-1].language == language:
            previous = segments[-1]
            segments[-1] = TTSSegment(language, previous.text + part)
        else:
            segments.append(TTSSegment(language, part))
    return segments


def select_tts_voice(
    text: str,
    english_voice: str,
    chinese_voice: str,
    malay_voice: str | None = None,
) -> str:
    """Choose the configured voice/language for a single-language text span."""
    if contains_han(text):
        return chinese_voice
    if detect_latin_language(text) == "ms":
        return malay_voice or english_voice
    return english_voice
