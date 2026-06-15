"""
Transcription worker — polls Firestore for queued jobs and processes them.

Usage:
    python worker.py              # real Whisper transcription
    TEST_MODE=true python worker.py   # returns a dummy SRT, skips Whisper
"""

import io
import os
import sys
import tempfile
import time

from dotenv import load_dotenv
load_dotenv()

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from firestore_client import claim_queued_job, complete_job, fail_job

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))
IDLE_SHUTDOWN_SECONDS = int(os.environ.get("IDLE_SHUTDOWN_SECONDS", "600"))  # 10 minutes
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

DUMMY_SRT = """\
1
00:00:00,000 --> 00:00:02,000
This is a test transcription.

2
00:00:02,000 --> 00:00:04,000
Whisper was skipped (TEST_MODE=true).
"""


def build_drive_service(tokens: dict):
    creds = Credentials(
        token=tokens["token"],
        refresh_token=tokens["refresh_token"],
        token_uri=tokens["token_uri"],
        client_id=tokens["client_id"],
        client_secret=tokens["client_secret"],
        scopes=tokens.get("scopes"),
    )
    return build("drive", "v3", credentials=creds)


def download_file(tokens: dict, file_id: str) -> str:
    """Download Drive file to a local temp file, return the path."""
    service = build_drive_service(tokens)

    # Get the file name so we can preserve the extension
    meta = service.files().get(fileId=file_id, fields="name").execute()
    file_name = meta.get("name", "audio")
    suffix = os.path.splitext(file_name)[1] or ".mp4"

    request = service.files().get_media(fileId=file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    downloader = MediaIoBaseDownload(tmp, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    tmp.close()
    return tmp.name


def transcribe(audio_path: str) -> str:
    """Run Whisper on *audio_path* and return SRT content as a string."""
    import whisper
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)

    segments = result.get("segments", [])
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = int(seconds) // 60 % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def process_job(job: dict):
    job_id = job["job_id"]
    file_id = job["file_id"]
    tokens = job.get("oauth_tokens")

    print(f"[worker] processing job {job_id} (file_id={file_id})")

    if TEST_MODE:
        print(f"[worker] TEST_MODE — returning dummy SRT")
        complete_job(job_id, DUMMY_SRT)
        return

    if not tokens:
        fail_job(job_id, "No OAuth tokens stored for this job.")
        return

    audio_path = None
    try:
        print(f"[worker] downloading file {file_id} from Drive...")
        audio_path = download_file(tokens, file_id)
        print(f"[worker] downloaded to {audio_path}, running Whisper...")
        srt = transcribe(audio_path)
        complete_job(job_id, srt)
        print(f"[worker] job {job_id} completed")
    except Exception as exc:
        print(f"[worker] job {job_id} failed: {exc}", file=sys.stderr)
        fail_job(job_id, str(exc))
    finally:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)


def shutdown_self():
    print("[worker] idle timeout reached — shutting down VM")
    os.system("sudo shutdown -h now")


def run():
    mode = "TEST" if TEST_MODE else "PRODUCTION"
    print(f"[worker] starting in {mode} mode, polling every {POLL_INTERVAL}s, "
          f"idle shutdown after {IDLE_SHUTDOWN_SECONDS}s")
    idle_since = time.monotonic()

    while True:
        try:
            job = claim_queued_job()
            if job:
                idle_since = time.monotonic()
                process_job(job)
                # Don't sleep — check immediately for more queued jobs
            else:
                idle_seconds = time.monotonic() - idle_since
                if not TEST_MODE and idle_seconds >= IDLE_SHUTDOWN_SECONDS:
                    shutdown_self()
                    break
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("[worker] shutting down")
            break
        except Exception as exc:
            print(f"[worker] unexpected error: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
