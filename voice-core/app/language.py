import re


_HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{3}")


def contains_han(text: str) -> bool:
    """Return whether text contains a CJK unified ideograph."""
    return bool(_HAN_PATTERN.search(text))


def contains_latin_word(text: str) -> bool:
    """Return whether enough Latin text is present to select an English voice."""
    return bool(_LATIN_WORD_PATTERN.search(text))


def select_tts_voice(text: str, english_voice: str, chinese_voice: str) -> str:
    """Choose a Kokoro voice whose language prefix matches the reply text."""
    return chinese_voice if contains_han(text) else english_voice
