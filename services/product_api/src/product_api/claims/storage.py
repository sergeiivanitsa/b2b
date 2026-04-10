import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from product_api.settings import Settings

UPLOAD_CHUNK_SIZE = 1024 * 1024
_FILENAME_ALLOWED_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_EXTENSION_ALLOWED_PATTERN = re.compile(r"^\.[A-Za-z0-9]{1,10}$")
_DEFAULT_MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".rtf": "application/rtf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


@dataclass(slots=True)
class StoredClaimUpload:
    filename: str
    storage_path: str
    mime_type: str
    size_bytes: int


def sanitize_original_filename(raw_filename: str | None) -> str:
    normalized = (raw_filename or "").strip().replace("\\", "/")
    basename = normalized.split("/")[-1] if normalized else ""
    safe = _FILENAME_ALLOWED_PATTERN.sub("_", basename).strip("._")
    if not safe:
        return "file"
    return safe[:120]


def normalize_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


async def save_claim_upload(
    settings: Settings,
    *,
    claim_id: int,
    upload_file: UploadFile,
) -> StoredClaimUpload:
    filename = sanitize_original_filename(upload_file.filename)
    extension = _safe_extension(filename)
    allowed_extensions = set(settings.claims_allowed_upload_extensions)
    if not extension or extension not in allowed_extensions:
        raise ValueError("unsupported extension")

    mime_type = normalize_content_type(upload_file.content_type)
    default_mime_type = _DEFAULT_MIME_BY_EXTENSION.get(extension, "application/octet-stream")
    if not mime_type or mime_type == "application/octet-stream":
        mime_type = default_mime_type

    base_dir = _resolve_base_dir(settings)
    storage_rel_path = Path("claims") / str(claim_id) / f"{uuid4().hex}{extension}"
    storage_abs_path = (base_dir / storage_rel_path).resolve()
    if not _is_within_dir(storage_abs_path, base_dir):
        raise ValueError("invalid storage path")

    storage_abs_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes = 0
    try:
        with storage_abs_path.open("wb") as handle:
            while True:
                chunk = await upload_file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > settings.claims_max_file_size_bytes:
                    raise ValueError("file is too large")
                handle.write(chunk)
    except Exception:
        _safe_unlink(storage_abs_path)
        raise

    if size_bytes == 0:
        _safe_unlink(storage_abs_path)
        raise ValueError("file is empty")

    return StoredClaimUpload(
        filename=filename,
        storage_path=storage_rel_path.as_posix(),
        mime_type=mime_type,
        size_bytes=size_bytes,
    )


def delete_claim_upload(settings: Settings, storage_path: str) -> None:
    if not storage_path:
        return
    base_dir = _resolve_base_dir(settings)
    target = (base_dir / storage_path).resolve()
    if not _is_within_dir(target, base_dir):
        return
    _safe_unlink(target)


def _resolve_base_dir(settings: Settings) -> Path:
    base_dir = Path(settings.claims_upload_dir).expanduser().resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _safe_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if _EXTENSION_ALLOWED_PATTERN.fullmatch(suffix):
        return suffix
    return ""


def _is_within_dir(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
