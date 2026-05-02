import base64
import binascii
import mimetypes
import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def save_uploaded_file(uploaded_file, folder: str) -> str:
    suffix = Path(uploaded_file.name).suffix or ".bin"
    filename = f"{folder}/{uuid.uuid4().hex}{suffix}"
    saved_path = default_storage.save(filename, uploaded_file)
    return default_storage.url(saved_path)


def save_data_url(data_url: str, folder: str) -> str:
    header, _, encoded = data_url.partition(",")
    mime_part = header.split(";")[0]
    mime_type = mime_part.replace("data:", "", 1) if mime_part.startswith("data:") else "application/octet-stream"
    extension = mimetypes.guess_extension(mime_type) or ".bin"
    filename = f"{folder}/{uuid.uuid4().hex}{extension}"
    try:
        binary = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        return data_url
    saved_path = default_storage.save(filename, ContentFile(binary))
    return default_storage.url(saved_path)


def persist_image_reference(value: str, folder: str) -> str:
    if not value:
        return value
    if value.startswith("data:image/"):
        return save_data_url(value, folder)
    return value

