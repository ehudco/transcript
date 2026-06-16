import os
from googleapiclient import discovery
from google.auth import default

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "whisper-project-462317")
ZONE = os.environ.get("VM_ZONE", "europe-west1-b")
INSTANCE_NAME = os.environ.get("VM_INSTANCE_NAME", "transcription-worker")

def get_compute_client():
    credentials, _ = default()
    return discovery.build("compute", "v1", credentials=credentials)

def get_vm_status() -> str:
    from googleapiclient.errors import HttpError
    client = get_compute_client()
    try:
        result = client.instances().get(
            project=PROJECT_ID,
            zone=ZONE,
            instance=INSTANCE_NAME
        ).execute()
        return result.get("status", "UNKNOWN")
    except HttpError as e:
        if e.resp.status == 404:
            return "NOT_FOUND"
        raise

def start_vm():
    client = get_compute_client()
    client.instances().start(
        project=PROJECT_ID,
        zone=ZONE,
        instance=INSTANCE_NAME
    ).execute()

def stop_vm():
    client = get_compute_client()
    client.instances().stop(
        project=PROJECT_ID,
        zone=ZONE,
        instance=INSTANCE_NAME
    ).execute()
