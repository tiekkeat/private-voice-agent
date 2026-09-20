def stt_language_options(language: str, prompt: str) -> dict[str, object]:
    """Build OpenAI-compatible STT options for auto or locked language mode."""
    options: dict[str, object] = {"prompt": prompt}
    if language == "auto":
        options["detect_language"] = True
    else:
        options["detect_language"] = False
        options["language"] = language
    return options
