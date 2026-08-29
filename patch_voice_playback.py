import sys

# Patch 1: Routing voice/audio media files through play_tts instead of send_voice in base.py
filepath_base = "/opt/hermes/gateway/platforms/base.py"
try:
    with open(filepath_base, "r") as f:
        code_base = f.read()

    target_base = """                        if should_send_media_as_audio(self.platform, ext, is_voice=is_voice):
                            media_result = await self.send_voice(
                                chat_id=event.source.chat_id,
                                audio_path=media_path,
                                metadata=_final_thread_metadata,
                                is_voice=is_voice,
                            )"""

    replacement_base = """                        if should_send_media_as_audio(self.platform, ext, is_voice=is_voice):
                            media_result = await self.play_tts(
                                chat_id=event.source.chat_id,
                                audio_path=media_path,
                                metadata=_final_thread_metadata,
                                is_voice=is_voice,
                            )"""

    if target_base in code_base:
        code_base = code_base.replace(target_base, replacement_base)
        with open(filepath_base, "w") as f:
            f.write(code_base)
        print("base.py voice playback routing patched successfully!")
    else:
        print("Warning: target_base not found in base.py!")
        sys.exit(1)
except Exception as e:
    print(f"Failed to patch base.py: {e}")
    sys.exit(1)


# Patch 2: Routing voice/audio media files through play_tts instead of send_voice in run.py
filepath_run = "/opt/hermes/gateway/run.py"
try:
    with open(filepath_run, "r") as f:
        code_run = f.read()

    target_run = """                    if should_send_media_as_audio(event.source.platform, ext, is_voice=is_voice):
                        await adapter.send_voice(
                            chat_id=event.source.chat_id,
                            audio_path=media_path,
                            metadata=_thread_meta,
                            is_voice=is_voice,
                        )"""

    replacement_run = """                    if should_send_media_as_audio(event.source.platform, ext, is_voice=is_voice):
                        await adapter.play_tts(
                            chat_id=event.source.chat_id,
                            audio_path=media_path,
                            metadata=_thread_meta,
                            is_voice=is_voice,
                        )"""

    if target_run in code_run:
        code_run = code_run.replace(target_run, replacement_run)
        with open(filepath_run, "w") as f:
            f.write(code_run)
        print("run.py voice playback routing patched successfully!")
    else:
        print("Warning: target_run not found in run.py!")
        sys.exit(1)
except Exception as e:
    print(f"Failed to patch run.py: {e}")
    sys.exit(1)
