from app.config import Settings
from app.model_setup import model_url
from app.language import (
    TTSSegment,
    contains_han,
    contains_latin_word,
    select_tts_voice,
    split_tts_segments,
)
from app.speech import stt_language_options


def test_base_urls_are_normalized() -> None:
    settings = Settings(
        livekit_api_key="key",
        livekit_api_secret="a-secret-that-is-at-least-32-bytes-long",
        public_livekit_url="wss://voice.test/livekit",
        llm_api_key="llm-key",
        llm_model="model",
        llm_base_url="https://example.test/v1/",
        stt_base_url="http://stt:8000/v1/",
        tts_base_url="http://tts:8880/v1/",
    )

    assert settings.llm_base_url == "https://example.test/v1"
    assert settings.stt_base_url == "http://stt:8000/v1"
    assert settings.tts_base_url == "http://tts:8880/v1"


def test_model_url_encodes_repository_separator() -> None:
    assert model_url(
        "http://stt:8000/v1/", "deepdml/faster-whisper-large-v3-turbo-ct2"
    ) == (
        "http://stt:8000/v1/models/"
        "deepdml%2Ffaster-whisper-large-v3-turbo-ct2"
    )


def test_mandarin_reply_selects_chinese_voice() -> None:
    assert contains_han("你好，今天怎么样？")
    assert select_tts_voice("你好！", "af_heart", "zf_xiaoxiao") == "zf_xiaoxiao"


def test_english_reply_selects_english_voice() -> None:
    assert not contains_han("Hello, how are you?")
    assert contains_latin_word("Hello")
    assert select_tts_voice("Hello!", "af_heart", "zf_xiaoxiao") == "af_heart"


def test_malay_reply_selects_malay_voice() -> None:
    assert select_tts_voice("Boleh, nanti saya balik.", "en", "zh", "ms") == "ms"


def test_mandarin_code_switching_stays_in_one_tts_request() -> None:
    assert split_tts_segments("Okay, 我等下 call you balik.") == [
        TTSSegment("zh", "Okay, 我等下 call you balik."),
    ]


def test_auto_stt_detects_language_with_prompt() -> None:
    assert stt_language_options("auto", "English or Mandarin") == {
        "detect_language": True,
        "prompt": "English or Mandarin",
    }


def test_locked_mandarin_stt_disables_detection() -> None:
    assert stt_language_options("zh", "Mandarin") == {
        "detect_language": False,
        "language": "zh",
        "prompt": "Mandarin",
    }
