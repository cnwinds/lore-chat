from __future__ import annotations

import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class IngestBody(BaseModel):
    text: str


class AskBody(BaseModel):
    query: str


class ResolveBody(BaseModel):
    choice: str


def _c(request: Request):
    return request.app.state.container


@router.post("/ingest")
async def ingest(body: IngestBody, request: Request):
    result = _c(request).organizer.ingest_text(body.text)
    return result.__dict__


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    ans = _c(request).retriever.answer(body.query)
    return ans.__dict__


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("未分类"),
):
    c = _c(request)
    data = await file.read()
    rel = c.repo.save_attachment(
        category,
        file.filename,
        data,
        commit_msg=f"add attachment {file.filename}",
    )
    abs_path = c.repo._abs(rel)
    from app.index.extract import extract_text

    text = extract_text(abs_path)
    if text.strip():
        c.indexer.reindex_doc(rel, text)
    c.repo.log_change(
        f"上传附件 {rel}",
        commit_msg=f"chore: changelog upload {file.filename}",
    )
    return {"attachment": rel, "indexed": bool(text.strip())}


@router.get("/download")
async def download(path: str, request: Request):
    try:
        data = _c(request).repo.get_attachment(path)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    filename = path.rsplit("/", 1)[-1]
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tree")
async def tree(request: Request):
    return {"docs": _c(request).repo.list_tree()}


@router.get("/doc")
async def doc(path: str, request: Request):
    try:
        d = _c(request).repo.read_doc(path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}


@router.get("/questions")
async def questions(request: Request):
    return {"questions": _c(request).pending.list_open()}


@router.post("/questions/{qid}/resolve")
async def resolve(qid: str, body: ResolveBody, request: Request):
    result = _c(request).organizer.resolve_pending(qid, body.choice)
    return result.__dict__
