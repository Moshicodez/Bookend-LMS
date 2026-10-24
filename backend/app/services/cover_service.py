from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

from ..exceptions import ValidationError


ALLOWED_COVER_EXTENSIONS = {".jpg", ".png", ".webp"}
MAX_COVER_SIZE = 2 * 1024 * 1024


class CoverService:
    def save(self, upload):
        if upload is None or not upload.filename:
            return None

        safe_name = secure_filename(upload.filename)
        extension = Path(safe_name).suffix.lower()
        if not safe_name or extension not in ALLOWED_COVER_EXTENSIONS:
            raise ValidationError("Cover images must be JPG, PNG, or WebP.")

        content = upload.stream.read(MAX_COVER_SIZE + 1)
        upload.stream.seek(0)
        if len(content) > MAX_COVER_SIZE:
            raise ValidationError("Cover images must be no larger than 2 MB.")
        if not self._has_valid_signature(content, extension):
            raise ValidationError("The uploaded file is not a valid image of that type.")

        filename = f"{uuid4().hex}{extension}"
        upload_directory = self._upload_directory()
        upload_directory.mkdir(parents=True, exist_ok=True)
        (upload_directory / filename).write_bytes(content)
        return filename

    def delete(self, filename):
        if not filename:
            return
        safe_filename = Path(filename).name
        (self._upload_directory() / safe_filename).unlink(missing_ok=True)

    @staticmethod
    def _upload_directory():
        configured_directory = current_app.config.get("COVER_UPLOAD_FOLDER")
        return Path(configured_directory or Path(current_app.static_folder) / "uploads")

    @staticmethod
    def _has_valid_signature(content, extension):
        if extension == ".jpg":
            return content.startswith(b"\xff\xd8\xff")
        if extension == ".png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        return (
            len(content) >= 12
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
        )
