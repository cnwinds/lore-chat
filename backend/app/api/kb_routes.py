from __future__ import annotations

import asyncio
import io
import json
from pathlib import PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.api.file_download import content_disposition_type, media_type_for_filename
from app.api.http_deps import (
    EnabledSkillsPutBody,
    KbDeleteBody,
    KbMoveBody,
    UpdateDocBody,
    container,
    kb_path_exists_detail,
    pack_path_choice_detail,
    kb_tree_service,
)
from app.engine.memory.constants import (
    MEMORY_FILE_DISABLED_MSG,
    is_memory_projection_path,
)
from app.engine.patch import diff_affected_range

router = APIRouter()


def _reject_oversized_video(data: bytes, name: str) -> None:
    from app.models.media import MAX_VIDEO_UPLOAD_BYTES, bytes_look_like_video

    if len(data) > MAX_VIDEO_UPLOAD_BYTES and bytes_look_like_video(data, name=name):
        limit_mb = MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(400, f"视频超过 {limit_mb}MB 上限")


def _raise_kb_import_error(exc: Exception, *, filename: str) -> None:
    from app.engine.kb_pack import PackPathChoiceError
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        suggest_alternate_filename,
    )

    if isinstance(exc, KbPathExistsError):
        raise HTTPException(
            409,
            detail=kb_path_exists_detail(
                exc.rel_path, str(exc), suggest_alternate_filename(filename)
            ),
        ) from exc
    if isinstance(exc, PackPathChoiceError):
        raise HTTPException(
            409,
            detail=pack_path_choice_detail(
                kind=exc.kind,
                original_path=exc.original_path,
                upload_path=exc.upload_path,
                default_path=exc.default_path,
                skills_dir=exc.skills_dir,
                message=str(exc),
            ),
        ) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


@router.get("/download")
async def download(
    path: str,
    request: Request,
    force_download: bool = Query(False, alias="download"),
):
    """打开文件：默认 inline 预览；download=1 强制下载。"""
    c = container(request)
    norm = path.replace("\\", "/").lstrip("/")
    if norm.startswith(".kb/") or norm.startswith(".git/"):
        raise HTTPException(404, "文件不存在")
    abs_p = c.repo.abs_path(norm)
    if not abs_p.is_file():
        raise HTTPException(404, "文件不存在")
    filename = abs_p.name
    media = media_type_for_filename(filename)
    disposition = content_disposition_type(
        media,
        force_download=force_download,
        filename=filename,
        sec_fetch_dest=request.headers.get("sec-fetch-dest"),
    )
    headers: dict[str, str] = {}
    # SVG 的 disposition 随 Sec-Fetch-Dest 变化；避免浏览器沿用旧的 attachment 缓存导致 <img> 空白
    if filename.lower().endswith(".svg"):
        headers["Cache-Control"] = "private, no-cache"
        headers["Vary"] = "Sec-Fetch-Dest"
    return FileResponse(
        path=abs_p,
        media_type=media,
        filename=filename,
        content_disposition_type=disposition,
        headers=headers,
    )


@router.get("/media/grant/{grant_id}")
async def media_grant(grant_id: str, request: Request):
    """短时媒体授权 URL：供 url_wire 多模态上游拉取，无需会话 cookie。"""
    from app.models.media import guess_video_mime, is_signed_media_file
    from app.models.media_grants import MediaGrantStore
    from app.models.vision import guess_mime

    c = container(request)
    grant = MediaGrantStore(c.settings.kb_path).resolve(grant_id)
    if grant is None:
        raise HTTPException(404, "授权不存在或已过期")
    norm = grant.rel_path
    if norm.startswith(".kb/") or norm.startswith(".git/"):
        raise HTTPException(404, "文件不存在")
    abs_p = c.repo.abs_path(norm)
    if not abs_p.is_file():
        raise HTTPException(404, "文件不存在")
    media_kind = is_signed_media_file(abs_p)
    if media_kind is not None:
        media = (
            guess_video_mime(str(abs_p))
            if media_kind == "video"
            else guess_mime(str(abs_p))
        )
        disposition = "inline"
    else:
        media = media_type_for_filename(abs_p.name)
        disposition = content_disposition_type(media, filename=abs_p.name)
    return FileResponse(
        path=abs_p,
        media_type=media,
        filename=abs_p.name,
        content_disposition_type=disposition,
    )


@router.get("/attachments/signed/{path:path}")
async def signed_attachment(path: str, token: str, request: Request):
    """短时签名附件 URL，供 url_wire 多模态模型拉取（图片或视频）。"""
    from app.models.media import guess_video_mime, is_signed_media_file
    from app.models.vision import (
        attachment_signing_secret,
        guess_mime,
        verify_attachment_token,
    )

    c = container(request)
    norm = path.replace("\\", "/").lstrip("/")
    if norm.startswith(".kb/") or norm.startswith(".git/"):
        raise HTTPException(404, "文件不存在")
    secret = attachment_signing_secret(c.settings)
    if not verify_attachment_token(rel_path=norm, token=token, secret=secret):
        raise HTTPException(403, "invalid or expired token")
    abs_p = c.repo.abs_path(norm)
    if not abs_p.is_file():
        raise HTTPException(404, "文件不存在")
    media_kind = is_signed_media_file(abs_p)
    if media_kind is None:
        raise HTTPException(403, "signed attachments are image/video only")
    media = guess_video_mime(str(abs_p)) if media_kind == "video" else guess_mime(str(abs_p))
    return FileResponse(
        path=abs_p,
        media_type=media,
        filename=abs_p.name,
        content_disposition_type="inline",
    )


@router.get("/download-zip")
async def download_zip(path: str, request: Request):
    from app.backup.export_kb import build_directory_zip

    c = container(request)
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        raise HTTPException(400, "请指定目录")
    if c.repo.is_protected(norm):
        raise HTTPException(403, "禁止下载该目录")
    try:
        buf = io.BytesIO()
        base_name = build_directory_zip(
            c.repo.root, norm, buf, skills_dir=c.settings.skills_dir
        )
        buf.seek(0)
    except FileNotFoundError:
        raise HTTPException(404, "目录不存在")
    except NotADirectoryError:
        raise HTTPException(400, "不是目录")
    filename = f"{base_name}.zip"
    from urllib.parse import quote

    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )


@router.get("/tree")
async def tree(request: Request):
    return {"docs": container(request).repo.list_tree()}


@router.get("/kb/discover-skills")
async def discover_skills(request: Request, from_dir: str = ""):
    _, svc = kb_tree_service(request)
    try:
        roots = svc.discover_skills(from_dir)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    return {"roots": roots}


@router.get("/enabled-skills")
async def get_enabled_skills(request: Request):
    c = container(request)
    return {"roots": c.enabled_skills.load_roots()}


@router.put("/enabled-skills")
async def put_enabled_skills(body: EnabledSkillsPutBody, request: Request):
    from app.engine.enabled_skills import EnabledSkillsError

    c = container(request)
    try:
        roots = c.enabled_skills.put(c.repo, list(body.roots or []))
    except EnabledSkillsError as e:
        raise HTTPException(400, str(e)) from e
    return {"roots": roots}


@router.post("/kb/import")
async def kb_import(
    request: Request,
    file: UploadFile = File(...),
    directory: str = Form(""),
    filename: str | None = Form(None),
    dest_root: str | None = Form(None),
):
    _, svc = kb_tree_service(request)
    name = (filename or file.filename or "upload.bin").strip()
    data = await file.read()
    _reject_oversized_video(data, name)
    from app.engine.kb_pack import PackPathChoiceError
    from app.engine.kb_tree_service import KbPathExistsError

    try:
        return svc.import_upload(
            directory=directory, filename=name, data=data, dest_root=dest_root
        )
    except (KbPathExistsError, PackPathChoiceError, PermissionError, ValueError) as e:
        _raise_kb_import_error(e, filename=name)
        raise


@router.post("/kb/import-batch")
async def kb_import_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    items: str = Form(...),
):
    from app.engine.kb_pack import PackPathChoiceError
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        MAX_KB_IMPORT_BATCH_FILES,
    )

    _, svc = kb_tree_service(request)
    try:
        specs = json.loads(items)
    except json.JSONDecodeError as e:
        raise HTTPException(400, "items 不是合法 JSON") from e
    if not isinstance(specs, list):
        raise HTTPException(400, "items 必须是数组")
    if len(files) != len(specs):
        raise HTTPException(400, "files 与 items 数量不一致")
    if len(files) > MAX_KB_IMPORT_BATCH_FILES:
        raise HTTPException(
            400, f"单次最多导入 {MAX_KB_IMPORT_BATCH_FILES} 个文件"
        )
    payloads: list[tuple[str, str, bytes]] = []
    for file, spec in zip(files, specs, strict=True):
        if not isinstance(spec, dict):
            raise HTTPException(400, "items 项必须是对象")
        directory = str(spec.get("directory") or "")
        name = str(spec.get("filename") or file.filename or "upload.bin").strip()
        data = await file.read()
        _reject_oversized_video(data, name)
        payloads.append((directory, name, data))
    try:
        return await asyncio.to_thread(svc.import_uploads, payloads)
    except (KbPathExistsError, PackPathChoiceError, PermissionError, ValueError) as e:
        hint = payloads[0][1] if payloads else "upload.bin"
        rel = getattr(e, "rel_path", None)
        if isinstance(rel, str) and rel:
            hint = PurePosixPath(rel).name or hint
        _raise_kb_import_error(e, filename=hint)
        raise


@router.post("/kb/move")
async def kb_move(body: KbMoveBody, request: Request):
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        suggest_alternate_filename,
    )

    _, svc = kb_tree_service(request)
    try:
        return svc.move(
            from_path=body.from_path,
            to_directory=body.to_directory,
            to_filename=body.to_filename,
        )
    except KbPathExistsError as e:
        raise HTTPException(
            409,
            detail=kb_path_exists_detail(
                e.rel_path,
                str(e),
                suggest_alternate_filename(
                    body.to_filename or body.from_path.rsplit("/", 1)[-1]
                ),
            ),
        ) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, "源路径不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/kb/delete")
async def kb_delete(body: KbDeleteBody, request: Request):
    _, svc = kb_tree_service(request)
    try:
        return svc.delete(body.path)
    except FileNotFoundError as e:
        raise HTTPException(404, "路径不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/doc")
async def doc(path: str, request: Request):
    try:
        d = container(request).repo.read_doc(path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}


@router.get("/doc/revisions")
async def doc_revisions(
    path: str,
    request: Request,
    limit: int = Query(80, ge=1, le=200),
):
    repo = container(request).repo
    try:
        revisions = repo.list_revisions(path, limit=limit)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"path": path, "revisions": revisions}


@router.get("/doc/revision")
async def doc_revision(path: str, sha: str, request: Request):
    repo = container(request).repo
    try:
        return repo.read_revision(path, sha)
    except FileNotFoundError:
        raise HTTPException(404, "该版本不存在")
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/doc")
async def update_doc(body: UpdateDocBody, request: Request):
    c = container(request)
    if is_memory_projection_path(body.path):
        raise HTTPException(400, MEMORY_FILE_DISABLED_MSG)
    if not c.repo.is_writable(body.path):
        raise HTTPException(403, "禁止编辑该路径")
    try:
        doc = c.repo.read_doc(body.path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    old_body = doc.body
    if old_body != body.body:
        affected_start, affected_end = diff_affected_range(old_body, body.body)
        c.knowledge_writer.save_edit(
            body.path,
            doc.meta,
            old_body,
            body.body,
            affected_start=affected_start,
            affected_end=affected_end,
            commit_msg=f"edit: {body.path}",
            changelog_line=f"用户编辑 {body.path}",
        )
    else:
        c.repo.write_doc(
            body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}"
        )
        c.repo.log_change(f"用户编辑 {body.path}")
    d = c.repo.read_doc(body.path)
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}
