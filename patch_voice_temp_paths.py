import sys

# Patch 1: Auto-TTS output path using DEFAULT_OUTPUT_DIR in base.py
filepath_base = "/opt/hermes/gateway/platforms/base.py"
try:
    with open(filepath_base, "r") as f:
        code_base = f.read()

    target_base = """    from tools.tts_tool import OPUS_VOICE_PLATFORMS

    ext = "ogg" if _platform_name(platform) in OPUS_VOICE_PLATFORMS else "mp3"
    audio_path = os.path.join(
        tempfile.gettempdir(),
        "hermes_voice",
        f"tts_reply_{uuid.uuid4().hex[:12]}.{ext}",
    )"""

    replacement_base = """    from tools.tts_tool import OPUS_VOICE_PLATFORMS, DEFAULT_OUTPUT_DIR

    ext = "ogg" if _platform_name(platform) in OPUS_VOICE_PLATFORMS else "mp3"
    audio_path = os.path.join(
        DEFAULT_OUTPUT_DIR,
        f"tts_reply_{uuid.uuid4().hex[:12]}.{ext}",
    )"""

    if target_base in code_base:
        code_base = code_base.replace(target_base, replacement_base)
        with open(filepath_base, "w") as f:
            f.write(code_base)
        print("base.py auto-TTS temp paths patched successfully!")
    else:
        print("Warning: target_base not found in base.py!")
        sys.exit(1)
except Exception as e:
    print(f"Failed to patch base.py temp path: {e}")
    sys.exit(1)


# Patch 2: play_ack temp output path using DEFAULT_OUTPUT_DIR in adapter.py
filepath_adapter = "/opt/hermes/plugins/platforms/discord/adapter.py"
try:
    with open(filepath_adapter, "r") as f:
        code_adapter = f.read()

    target_adapter = """        # Synthesise the ack via the configured TTS provider, then layer it.
        import uuid as _uuid
        audio_path = os.path.join(
            tempfile.gettempdir(), "hermes_voice",
            f"ack_{_uuid.uuid4().hex[:12]}.mp3",
        )
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)"""

    replacement_adapter = """        # Synthesise the ack via the configured TTS provider, then layer it.
        import uuid as _uuid
        from tools.tts_tool import DEFAULT_OUTPUT_DIR
        audio_path = os.path.join(
            DEFAULT_OUTPUT_DIR,
            f"ack_{_uuid.uuid4().hex[:12]}.mp3",
        )
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)"""

    if target_adapter in code_adapter:
        code_adapter = code_adapter.replace(target_adapter, replacement_adapter)
        with open(filepath_adapter, "w") as f:
            f.write(code_adapter)
        print("adapter.py ack temp paths patched successfully!")
    else:
        print("Warning: target_adapter not found in adapter.py!")
        sys.exit(1)
except Exception as e:
    print(f"Failed to patch adapter.py temp path: {e}")
    sys.exit(1)
