from app.config import Settings
from app.model_setup import model_url
from app.language import contains_han, contains_latin_word, select_tts_voice


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
