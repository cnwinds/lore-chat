from __future__ import annotations

import io

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api.http_deps import (
    KbDeleteBody,
    KbMoveBody,
    UpdateDocBody,
    container,
    kb_path_exists_detail,
    kb_tree_service,
)
from app.engine.patch import diff_affected_range

router = APIRouter()


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("未分类"),
):
    c = container(request)
    data = await file.read()
    rel = c.repo.save_attachment(
        category,
        file.filename,
        data,
        commit_msg=f"add attachment {file.filename}",
    )
    abs_path = c.repo.abs_path(rel)
    from app.index.extract import extract_text

    text = extract_text(abs_path)
    indexed = c.knowledge_writer.index_extracted_text(rel, text)
    c.repo.log_change(
        f"上传附件 {rel}",
        commit_msg=f"chore: changelog upload {file.filename}",
    )
    return {"attachment": rel, "indexed": indexed}


@router.get("/download")
async def download(path: str, request: Request):
    c = container(request)
    norm = path.replace("\\", "/").lstrip("/")
    if norm.startswith(".kb/") or norm.startswith(".git/"):
        raise HTTPException(404, "文件不存在")
    try:
        data = c.repo.get_attachment(norm)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    filename = norm.rsplit("/", 1)[-1]
    media = (
        "text/markdown; charset=utf-8"
        if norm.lower().endswith(".md")
        else "application/octet-stream"
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    if not c.repo.is_writable(body.path):
        raise HTTPException(403, "禁止编辑该路径")
    try:
        doc = c.repo.read_doc(body.path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    old_body = doc.body
    norm_path = body.path.replace("\\", "/")
    if norm_path == "系统/记忆.md":
        sync = c.memory_service.import_manual_document(
            doc.meta, body.body, dry_run=True
        )
        if not sync.get("ok"):
            raise HTTPException(400, sync.get("message", "记忆同步失败"))
        c.repo.write_doc(
            body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}"
        )
        sync = c.memory_service.import_manual_document(doc.meta, body.body)
        if not sync.get("ok"):
            c.repo.write_doc(
                body.path, doc.meta, old_body, commit_msg=f"rollback: {body.path}"
            )
            raise HTTPException(400, sync.get("message", "记忆同步失败"))
        c.knowledge_writer.drop_from_index([body.path])
    else:
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
