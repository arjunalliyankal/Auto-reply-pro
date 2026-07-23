import os
import requests
from groq import Groq

# Groq Whisper-accepted formats
WHISPER_SUPPORTED = {'.flac', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.ogg', '.opus', '.wav', '.webm'}

# Audio extensions we recognise as audio input
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.oga', '.m4a', '.aac', '.flac', '.opus', '.webm', '.mp4'}

# ── Ensure static-ffmpeg binary is in PATH at import time ────────────────────
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()          # downloads ffmpeg binary if needed
    print("[AudioProcessor] static-ffmpeg ready.")
except Exception as _sfex:
    print(f"[AudioProcessor] static-ffmpeg setup warning: {_sfex}")


def _convert_to_wav(src_path: str, wav_path: str) -> bool:
    """
    Convert any audio file to WAV using pydub (backed by static-ffmpeg).
    Returns True on success, False on failure.
    """
    print(f"[AudioProcessor] Converting '{src_path}' -> WAV...")
    try:
        from pydub import AudioSegment
        ext = os.path.splitext(src_path)[1].lower().lstrip(".")
        if ext == "oga":
            ext = "ogg"                    # pydub identifies Ogg Opus as "ogg"
        print(f"[AudioProcessor] Reading format='{ext}' from '{src_path}'")
        audio = AudioSegment.from_file(src_path, format=ext)
        audio.export(wav_path, format="wav")
        print(f"[AudioProcessor] Conversion OK -> '{wav_path}' ({os.path.getsize(wav_path)} bytes)")
        return True
    except Exception as e:
        print(f"[AudioProcessor] Conversion to WAV failed: {e}")
        return False


def is_audio(input_val) -> bool:
    """
    Returns True if:
      - input_val is a string path whose extension is a known audio format, OR
      - input_val is a Telegram update dict that contains a 'voice' or 'audio' key.
    """
    if isinstance(input_val, str):
        return os.path.splitext(input_val)[1].lower() in AUDIO_EXTENSIONS

    if isinstance(input_val, dict):
        msg = input_val.get("message", {})
        return "voice" in msg or "audio" in msg

    return False


def _transcribe_file(client: Groq, file_path: str) -> str:
    """
    Send a single audio file to Groq Whisper and return the transcript.
    If the file format is not natively accepted by Whisper, convert to WAV first.
    """
    ext = os.path.splitext(file_path)[1].lower()
    wav_path = None

    if ext not in WHISPER_SUPPORTED or ext == ".oga":
        # Convert to WAV so Whisper always gets a format it accepts
        wav_path = file_path.rsplit(".", 1)[0] + "_converted.wav"
        if not _convert_to_wav(file_path, wav_path):
            return ""
        send_path = wav_path
    else:
        send_path = file_path

    try:
        with open(send_path, "rb") as f:
            data = f.read()
        print(f"[AudioProcessor] Sending '{os.path.basename(send_path)}' ({len(data)} bytes) to Whisper...")
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(send_path), data),
            model="whisper-large-v3",
            response_format="text",
        )
        return transcription.strip()
    except Exception as e:
        print(f"[AudioProcessor] Whisper transcription error: {e}")
        return ""
    finally:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


def transcribe_audio(input_val, api_key: str, bot_token: str = None) -> str:
    """
    Transcribes audio input to text using Groq Whisper.

    Handles:
      - A Telegram update dict containing voice/audio — downloads the file first.
      - A local file path string.

    Any unsupported format (e.g. .oga) is converted to WAV via pydub/static-ffmpeg.
    """
    if not api_key:
        return ""

    client = Groq(api_key=api_key)
    os.makedirs("data", exist_ok=True)
    temp_path = None

    try:
        # ── Telegram voice/audio update ──────────────────────────────────────
        if isinstance(input_val, dict):
            msg = input_val.get("message", {})
            voice_or_audio = msg.get("voice") or msg.get("audio")
            if not voice_or_audio or not bot_token:
                return ""

            file_id = voice_or_audio["file_id"]

            # 1. Resolve file path on Telegram servers
            resp = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                params={"file_id": file_id},
                timeout=10,
            )
            resp.raise_for_status()
            tg_file_path = resp.json()["result"]["file_path"]

            # 2. Download raw bytes
            dl_resp = requests.get(
                f"https://api.telegram.org/file/bot{bot_token}/{tg_file_path}",
                timeout=20,
            )
            dl_resp.raise_for_status()

            # 3. Write to a temp file keeping the original extension
            ext = os.path.splitext(tg_file_path)[1] or ".oga"
            temp_path = f"data/temp_voice{ext}"
            with open(temp_path, "wb") as f:
                f.write(dl_resp.content)

            return _transcribe_file(client, temp_path)

        # ── Local file path ───────────────────────────────────────────────────
        elif isinstance(input_val, str) and os.path.exists(input_val):
            return _transcribe_file(client, input_val)

    except Exception as e:
        print(f"[AudioProcessor] Error processing audio input: {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return ""
