from __future__ import annotations

import io

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
    kb_tree_service,
)
from app.engine.memory.constants import (
    MEMORY_FILE_DISABLED_MSG,
    is_memory_projection_path,
)
from app.engine.patch import diff_affected_range

router = APIRouter()


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
    if media_kind is None:
        raise HTTPException(403, "media grants are image/video only")
    media = guess_video_mime(str(abs_p)) if media_kind == "video" else guess_mime(str(abs_p))
    return FileResponse(
        path=abs_p,
        media_type=media,
        filename=abs_p.name,
        content_disposition_type="inline",
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
        base_name = build_directory_zip(c.repo.root, norm, buf)
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
):
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        suggest_alternate_filename,
    )

    _, svc = kb_tree_service(request)
    name = (filename or file.filename or "upload.bin").strip()
    data = await file.read()
    from app.models.media import MAX_VIDEO_UPLOAD_BYTES, bytes_look_like_video

    if len(data) > MAX_VIDEO_UPLOAD_BYTES and bytes_look_like_video(data, name=name):
        limit_mb = MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(400, f"视频超过 {limit_mb}MB 上限")
    try:
        return svc.import_upload(directory=directory, filename=name, data=data)
    except KbPathExistsError as e:
        raise HTTPException(
            409,
            detail=kb_path_exists_detail(
                e.rel_path, str(e), suggest_alternate_filename(name)
            ),
        ) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


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
