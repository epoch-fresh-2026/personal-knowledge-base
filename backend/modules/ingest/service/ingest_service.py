"""Issue #52：统一收录流程（解析→切分→Embedding→单事务保存）。

职责：
- 文件上传：先写临时目录 → 解析 → 空内容判定 → 切分 → Embedding →
  临时文件转正式文件 → 单事务保存 Document/Chunk；任一步失败均补偿清理，
  不留下可被列表/下载/检索使用的半成品。
- URL 收录：基础 URL 校验 → 抓取 → 空内容判定 → 切分 → Embedding →
  单事务保存 Document/Chunk；source_url 保存用户提交的原始 URL。

设计约束：
- Embedding 只调用共享能力 embedding_service.generate_chunk_embeddings
  （其底层为 shared.embedding.get_embedding），本模块不复制供应商请求实现。
- 临时目录独立于正式 uploads 目录，且临时文件不创建任何 Document 记录，
  因此不会被普通文档列表/下载/检索接口当作正式文档使用。
- 与 Issue #47 的 .orphan_cleanup.json（彻底删除后的文件残留补偿）职责分离：
  本模块只处理"本次收录事务内"的临时/正式文件，不触碰该清单。
"""

import logging
import os
import shutil
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
import docx

from modules.ingest.domain.models import Document, Chunk
from modules.ingest.repository.document_repo import save_document
from modules.ingest.service.splitter import split_markdown
from modules.ingest.service.embedding_service import generate_chunk_embeddings

logger = logging.getLogger(__name__)

# 正式上传目录；source_url 前缀保持既有 /uploads/ 约定。
UPLOAD_DIR = "uploads"
UPLOAD_URL_PREFIX = "/uploads/"
# 临时目录独立，避免被当作正式文档；可通过 monkeypatch 注入测试目录。
TEMP_DIR = ".ingest_tmp"

TEXT_EXTENSIONS = (
    ".md", ".txt", ".py", ".java", ".cpp", ".c",
    ".js", ".ts", ".html", ".css", ".json", ".sql",
    ".go", ".rs",
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg")


class IngestError(Exception):
    """收录失败，携带面向用户的失败原因与建议 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _safe_remove(path: str, stage: str) -> None:
    """尽力删除单个文件；删除失败时记录失败信息，不静默跳过。

    记录内容（轻量 logging，不引入新清单/补偿系统，与 #47 的
    .orphan_cleanup.json 职责严格分离）：
    - path：待清理文件路径；
    - stage：清理阶段（临时文件清理 / 正式文件补偿清理）；
    - reason：删除失败的异常原因。

    清理异常只记录、不向上抛出，因此不会覆盖 finally 中正在传播的
    原始收录异常（规则 4）；收录成功路径不调用本函数（规则 5）。
    """
    try:
        os.remove(path)
    except OSError as e:
        logger.error(
            "收录文件清理失败：path=%s, stage=%s, reason=%s",
            path, stage, e,
        )


def _safe_upload_name(original_filename: str) -> str:
    """将用户文件名收敛为纯文件名，剔除 POSIX / Windows 目录成分。"""
    if not isinstance(original_filename, str) or not original_filename.strip():
        raise IngestError("文件名不能为空", 400)
    # 统一分隔符后只保留最后一段，杜绝 ../、..\ 等目录穿越写法。
    base = original_filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not base or base in (".", "..") or "\x00" in base:
        raise IngestError("文件名不合法", 400)
    return base


def _inside_directory(directory: str, name: str) -> str:
    """构造目标路径并验证其真实位置位于 directory 内，拒绝任何越界。"""
    root = os.path.realpath(directory)
    candidate = os.path.realpath(os.path.join(root, name))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise IngestError("文件名不合法：目标路径越界", 400)
    except ValueError as e:
        # Windows 上不同盘符的 commonpath 会抛 ValueError，同样视为越界。
        raise IngestError("文件名不合法：目标路径越界", 400) from e
    return candidate


def _parse_uploaded_file(file_path: str, filename: str) -> tuple[str, str, bool]:
    """解析本地临时文件。

    返回 (content, source_type, is_text_class)：
    - is_text_class=True 表示文本/PDF/DOCX 类，解析为空须终止收录；
    - 图片/视频/未知文件返回占位文本，is_text_class=False，
      不因缺少 OCR/ASR 而失败，也不被误判为普通文件解析失败。
    解析异常原样抛出，由上层包装为明确失败原因。
    """
    lower = filename.lower()

    if lower.endswith(".pdf"):
        reader = PdfReader(file_path)
        content = "".join(
            (page.extract_text() or "") + "\n" for page in reader.pages
        )
        return content, "file", True

    if lower.endswith(".docx"):
        document = docx.Document(file_path)
        content = "".join(para.text + "\n" for para in document.paragraphs)
        return content, "file", True

    if lower.endswith(TEXT_EXTENSIONS):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return content, "file", True

    if lower.endswith(IMAGE_EXTENSIONS):
        return f"【图片文件】{filename}", "image", False

    if lower.endswith(VIDEO_EXTENSIONS):
        return f"【视频文件】{filename}", "video", False

    return f"【未知文件】{filename}", "file", False


def _build_chunks(doc_id: str, chunks_text: list[str]) -> list[Chunk]:
    return [
        Chunk(
            id=str(uuid4()),
            document_id=doc_id,
            content=text,
            embedding=None,
            chunk_index=i,
        )
        for i, text in enumerate(chunks_text)
    ]


def _split_or_fail(content: str, empty_message: str) -> list[str]:
    try:
        chunks_text = split_markdown(content)
    except Exception as e:
        raise IngestError(f"文本切分失败：{e}") from e
    if not chunks_text:
        raise IngestError(empty_message, 400)
    return chunks_text


async def _embed_or_fail(chunks: list[Chunk]) -> None:
    """任一 chunk 的 Embedding 失败 → 整个收录失败（规则 A）。"""
    try:
        await generate_chunk_embeddings(chunks)
    except Exception as e:
        raise IngestError(f"Embedding 生成失败：{e}") from e


async def ingest_upload_file(
    db,
    file_bytes: bytes,
    original_filename: str,
    is_public: bool,
    user_id: str,
) -> dict:
    """文件收录：临时文件 → 解析 → 切分 → Embedding → 转正式 → 单事务保存。"""
    safe_filename = _safe_upload_name(original_filename)
    doc_id = str(uuid4())
    unique_filename = f"{uuid4()}_{safe_filename}"
    os.makedirs(TEMP_DIR, exist_ok=True)
    tmp_path = _inside_directory(TEMP_DIR, unique_filename)
    final_path = _inside_directory(UPLOAD_DIR, unique_filename)

    moved = False
    committed = False
    try:
        # 1. 先写临时文件（不在正式目录，不创建 Document）
        with open(tmp_path, "wb") as buffer:
            buffer.write(file_bytes)

        # 2. 解析（异常 → 明确失败）
        try:
            content, source_type, is_text_class = _parse_uploaded_file(
                tmp_path, original_filename
            )
        except Exception as e:
            raise IngestError(f"文件解析失败：{e}", 400) from e

        # 3. 空内容判定：仅文本类；占位文本不算解析失败
        if is_text_class and not content.strip():
            raise IngestError("文件内容为空或无法解析，未创建文档", 400)

        # 4. 切分
        chunks_text = _split_or_fail(content, "文件切分结果为空，未创建文档")
        chunks = _build_chunks(doc_id, chunks_text)

        # 5. Embedding（共享能力；全部 chunk 成功后才继续）
        await _embed_or_fail(chunks)

        # 6. 临时文件转正式文件
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        try:
            shutil.move(tmp_path, final_path)
            moved = True
        except OSError as e:
            raise IngestError(f"正式文件保存失败：{e}") from e

        # 7. 单事务保存 Document + 全部 Chunk
        doc = Document(
            id=doc_id,
            title=original_filename,
            source_type=source_type,
            source_url=f"{UPLOAD_URL_PREFIX}{unique_filename}",
            is_public=is_public,
            owner_id=user_id,
        )
        try:
            save_document(db, doc, chunks)
            committed = True
        except Exception as e:
            db.rollback()
            raise IngestError(f"文档保存失败：{e}") from e

        return {
            "id": doc_id,
            "title": doc.title,
            "chunks_count": len(chunks),
        }
    finally:
        # 失败补偿：未提交时删除已移动的正式文件，或尚未移动的临时文件。
        # 成功（committed=True）时正式文件保留，不做任何清理（规则 5）。
        # moved=True 时临时文件已被 shutil.move 消费、本就不存在，改为
        # if/else 分支，避免对已消失的临时文件产生"清理失败"误报。
        if not committed:
            if moved:
                _safe_remove(final_path, "正式文件补偿清理")
            else:
                _safe_remove(tmp_path, "临时文件清理")


def _validate_http_url(url: str) -> None:
    """仅接受带 scheme 与 hostname 的 http/https URL（网络请求前校验）。"""
    if not isinstance(url, str) or not url.strip():
        raise IngestError("URL 不能为空", 400)
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
    except ValueError as e:
        raise IngestError(f"URL 格式不合法：{e}", 400) from e
    if parsed.scheme not in ("http", "https") or not hostname:
        raise IngestError("URL 格式不合法：仅支持带主机名的 http/https 地址", 400)


async def ingest_web_url(
    db,
    url: str,
    is_public: bool,
    user_id: str,
) -> dict:
    """URL 收录：校验 → 抓取 → 切分 → Embedding → 单事务保存；保存原始 URL。"""
    _validate_http_url(url)

    # 1. 抓取并提取正文
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
        content = BeautifulSoup(resp.text, "html.parser").get_text(
            separator="\n", strip=True
        )
    except Exception as e:
        raise IngestError(f"抓取失败：{e}", 400) from e

    if not content.strip():
        raise IngestError("网页内容为空，无法收录", 400)

    # 2. 切分
    chunks_text = _split_or_fail(content, "网页切分结果为空，无法收录")

    doc_id = str(uuid4())
    chunks = _build_chunks(doc_id, chunks_text)

    # 3. Embedding（共享能力；任一 chunk 失败整体失败）
    await _embed_or_fail(chunks)

    # 4. 单事务保存；source_url 为用户提交的原始 URL（不取重定向地址）
    doc = Document(
        id=doc_id,
        title=url,
        source_type="url",
        source_url=url,
        is_public=is_public,
        owner_id=user_id,
    )
    try:
        save_document(db, doc, chunks)
    except Exception as e:
        db.rollback()
        raise IngestError(f"网页文档保存失败：{e}") from e

    return {
        "id": doc_id,
        "title": doc.title,
        "chunks_count": len(chunks),
    }
