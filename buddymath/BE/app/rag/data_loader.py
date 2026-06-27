"""
data_loader.py – Tự động scan thư mục data/ và ingest tài liệu vào RAGEngine.

Quy ước thư mục:
  data/{subject}/{topic}/file.pdf|docx|txt|md...

Manifest JSON theo dõi mtime → chỉ xử lý file mới/đã sửa.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import DATA_ROOT, MANIFEST_PATH
from app.rag.chunking import DocumentChunker

if TYPE_CHECKING:
    from app.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md", ".markdown", ".tex"}


class DataDirectoryLoader:
    """Quét data_root và nạp tài liệu mới/đã sửa vào RAGEngine."""

    def __init__(self, data_root: Path = DATA_ROOT, manifest_path: Path = MANIFEST_PATH):
        self.data_root     = data_root
        self.manifest_path = manifest_path
        self.chunker       = DocumentChunker()

    # ── Manifest ─────────────────────────────────────────────────────────────
    def _load_manifest(self) -> dict[str, float]:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Không đọc được manifest, sẽ re-ingest tất cả: {exc}")
        return {}

    def _save_manifest(self, manifest: dict[str, float]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Scan ─────────────────────────────────────────────────────────────────
    def scan(self) -> list[dict]:
        if not self.data_root.exists():
            logger.info(f"Tạo thư mục data: {self.data_root}")
            self.data_root.mkdir(parents=True, exist_ok=True)
            return []

        found: list[dict] = []
        for subject_dir in sorted(self.data_root.iterdir()):
            if not subject_dir.is_dir() or subject_dir.name.startswith("."):
                continue
            for topic_dir in sorted(subject_dir.iterdir()):
                if not topic_dir.is_dir() or topic_dir.name.startswith("."):
                    continue
                for file_path in sorted(topic_dir.iterdir()):
                    if file_path.suffix.lower() in SUPPORTED_EXT:
                        found.append({
                            "path":    file_path,
                            "subject": subject_dir.name,
                            "topic":   topic_dir.name,
                        })

        logger.info(f"DataLoader tìm thấy {len(found)} tài liệu trong '{self.data_root}'")
        return found

    # ── Ingest ───────────────────────────────────────────────────────────────
    def ingest_all(self, rag_engine: "RAGEngine", force: bool = False) -> dict:
        manifest   = {} if force else self._load_manifest()
        file_descs = self.scan()

        new_files = skip_files = total_chunks = 0
        errors: list[str] = []

        for fd in file_descs:
            path:    Path = fd["path"]
            subject: str  = fd["subject"]
            topic:   str  = fd["topic"]
            key   = str(path.resolve())
            mtime = path.stat().st_mtime

            if not force and key in manifest and abs(manifest[key] - mtime) < 1.0:
                skip_files += 1
                logger.debug(f"Bỏ qua (đã có): {path.name}")
                continue

            try:
                logger.info(f"Đang ingest: {path.name}  [{subject}/{topic}]")
                chunks = self.chunker.chunk_file(file_path=str(path), subject=subject, topic=topic)
                # Luôn đánh dấu đã xử lý (dù 0 chunk) để lần sau không lặp lại
                manifest[key] = mtime
                if chunks:
                    rag_engine.add_documents(chunks)
                    total_chunks += len(chunks)
                    new_files    += 1
                    logger.info(f"  ✓ {path.name} → {len(chunks)} chunks ({subject}/{topic})")
                else:
                    logger.warning(f"  ⚠ {path.name} không tạo được chunk nào.")
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
                logger.error(f"  ✗ Lỗi khi ingest '{path}': {exc}", exc_info=True)

        self._save_manifest(manifest)

        summary = {
            "total_files_found":  len(file_descs),
            "new_files_ingested": new_files,
            "skipped_files":      skip_files,
            "total_chunks":       total_chunks,
            "errors":             errors,
        }
        logger.info(f"DataLoader hoàn tất: {summary}")
        return summary

    # ── Cấu trúc thư mục ───────────────────────────────────────────────────────
    def list_structure(self) -> dict[str, list[str]]:
        structure: dict[str, list[str]] = {}
        if not self.data_root.exists():
            return structure

        for subject_dir in sorted(self.data_root.iterdir()):
            if not subject_dir.is_dir() or subject_dir.name.startswith("."):
                continue
            topics = sorted(
                d.name for d in subject_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            if topics:
                structure[subject_dir.name] = topics
        return structure

    def get_topic_files(self, subject: str, topic: str) -> list[str]:
        topic_dir = self.data_root / subject / topic
        if not topic_dir.exists():
            return []
        return sorted(f.name for f in topic_dir.iterdir() if f.suffix.lower() in SUPPORTED_EXT)
