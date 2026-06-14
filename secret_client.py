from google.cloud import secretmanager
import os

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "transcription-platform")

def get_secret(name: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{PROJECT_ID}/secrets/{name}/versions/latest"
    response = client.access_secret_version(request={"name": secret_name})
    return response.payload.data.decode("UTF-8")
