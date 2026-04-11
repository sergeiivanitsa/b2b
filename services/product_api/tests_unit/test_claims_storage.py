from io import BytesIO
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from product_api.claims.storage import (
    delete_claim_upload,
    sanitize_original_filename,
    save_claim_upload,
)
from product_api.settings import get_settings


def _make_upload(filename: str, content_type: str, payload: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(payload),
        headers=Headers({"content-type": content_type}),
    )


def _make_settings(tmp_path: Path):
    return get_settings().model_copy(
        update={
            "claims_upload_dir": str(tmp_path),
            "claims_max_file_size_bytes": 64,
            "claims_allowed_upload_extensions": [".pdf", ".png"],
        }
    )


def test_sanitize_original_filename_removes_path_and_unsafe_chars():
    assert sanitize_original_filename("../../foo/bar contract?.pdf") == "bar contract_.pdf"
    assert sanitize_original_filename("договор.pdf") == "договор.pdf"
    assert sanitize_original_filename("") == "file"


@pytest.mark.asyncio
async def test_save_claim_upload_success(tmp_path: Path):
    settings = _make_settings(tmp_path)
    upload = _make_upload("../contract.pdf", "application/pdf", b"%PDF-1.4")

    stored = await save_claim_upload(settings, claim_id=42, upload_file=upload)

    assert stored.filename == "contract.pdf"
    assert stored.storage_path.startswith("claims/42/")
    assert ".." not in stored.storage_path
    assert stored.mime_type == "application/pdf"
    assert stored.size_bytes == len(b"%PDF-1.4")
    assert (tmp_path / stored.storage_path).is_file()


@pytest.mark.asyncio
async def test_save_claim_upload_rejects_unsupported_extension(tmp_path: Path):
    settings = _make_settings(tmp_path)
    upload = _make_upload("contract.gif", "image/gif", b"GIF89a")

    with pytest.raises(ValueError, match="unsupported extension"):
        await save_claim_upload(settings, claim_id=7, upload_file=upload)


@pytest.mark.asyncio
async def test_save_claim_upload_rejects_too_large_file_and_cleans_up(tmp_path: Path):
    settings = get_settings().model_copy(
        update={
            "claims_upload_dir": str(tmp_path),
            "claims_max_file_size_bytes": 4,
            "claims_allowed_upload_extensions": [".pdf"],
        }
    )
    upload = _make_upload("contract.pdf", "application/pdf", b"12345")

    with pytest.raises(ValueError, match="file is too large"):
        await save_claim_upload(settings, claim_id=8, upload_file=upload)

    claim_dir = tmp_path / "claims" / "8"
    if claim_dir.exists():
        assert list(claim_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_save_claim_upload_accepts_docx_with_octet_stream_content_type(tmp_path: Path):
    settings = get_settings().model_copy(
        update={
            "claims_upload_dir": str(tmp_path),
            "claims_max_file_size_bytes": 64,
            "claims_allowed_upload_extensions": [".docx"],
        }
    )
    upload = _make_upload("contract.docx", "application/octet-stream", b"PK\x03\x04")

    stored = await save_claim_upload(settings, claim_id=9, upload_file=upload)

    assert stored.filename == "contract.docx"
    assert stored.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert stored.storage_path.endswith(".docx")
    assert (tmp_path / stored.storage_path).is_file()


@pytest.mark.asyncio
async def test_save_claim_upload_accepts_allowed_extension_with_nonstandard_mime(tmp_path: Path):
    settings = get_settings().model_copy(
        update={
            "claims_upload_dir": str(tmp_path),
            "claims_max_file_size_bytes": 64,
            "claims_allowed_upload_extensions": [".pdf"],
        }
    )
    upload = _make_upload("contract.pdf", "application/x-custom-pdf", b"%PDF-1.4")

    stored = await save_claim_upload(settings, claim_id=10, upload_file=upload)

    assert stored.filename == "contract.pdf"
    assert stored.mime_type == "application/x-custom-pdf"
    assert stored.storage_path.endswith(".pdf")
    assert (tmp_path / stored.storage_path).is_file()


@pytest.mark.asyncio
async def test_save_claim_upload_accepts_cyrillic_filename_and_preserves_name(tmp_path: Path):
    settings = get_settings().model_copy(
        update={
            "claims_upload_dir": str(tmp_path),
            "claims_max_file_size_bytes": 64,
            "claims_allowed_upload_extensions": [".pdf"],
        }
    )
    upload = _make_upload("договор.pdf", "application/pdf", b"%PDF-1.4")

    stored = await save_claim_upload(settings, claim_id=11, upload_file=upload)

    assert stored.filename == "договор.pdf"
    assert stored.storage_path.endswith(".pdf")
    assert (tmp_path / stored.storage_path).is_file()


def test_delete_claim_upload_does_not_traverse_outside_base(tmp_path: Path):
    settings = _make_settings(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("keep", encoding="utf-8")

    delete_claim_upload(settings, "../outside.txt")
    assert outside.read_text(encoding="utf-8") == "keep"
