"""
CLI — Ingestão de PSs históricas (Onda 5 close).

Walk numa pasta de DAMs/PSs legados → anonimiza → embed → Qdrant.

Uso:
  python scripts/ingest_historical_proposals.py --root "/path" [--limit N] [--no-llm-review] [--dry-run]

Geração de output:
  data/ingest_manifest.csv     — uma linha por arquivo processado
  data/ingest_samples/         — 50 amostras .txt de chunks já anonimizados
                                  pra spot-check manual de vazamento de PII

Concorrência: paralelismo bounded por --workers (default 4). Embedding +
Qdrant são I/O-bound, então threads sobre asyncio funciona bem aqui.

Falhas individuais NÃO param a corrida — vão pro manifest com status=erro.
A corrida só aborta em erro fatal (Qdrant unreachable, etc).

Nota sobre .doc: requer libreoffice instalado (apt install libreoffice-core
libreoffice-writer). Se ausente, .doc é pulado com status=skipped_no_libreoffice.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

# Ensure backend/ é importável quando rodado de scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ingest.pipeline import IngestPipeline, IngestResult  # noqa: E402
from services.propostai.agents.llm_client import LLMClient  # noqa: E402
from services.rag.service import RAGService  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST_PATH = DATA_DIR / "ingest_manifest.csv"
SAMPLES_DIR = DATA_DIR / "ingest_samples"

SUPPORTED_DIRECT = {".docx", ".pdf", ".xlsx"}
SUPPORTED_CONVERT = {".doc"}  # via libreoffice


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest historical PSs into Sócrates corpus")
    p.add_argument("--root", required=True, help="Root directory to scan recursively")
    p.add_argument("--limit", type=int, default=0, help="Stop after N docs (0=all)")
    p.add_argument("--workers", type=int, default=4, help="Parallel pipelines")
    p.add_argument("--no-llm-review", action="store_true", help="Skip LLM second-pass anonymization")
    p.add_argument("--dry-run", action="store_true", help="Process & anonymize but don't upsert to Qdrant")
    p.add_argument("--samples", type=int, default=50, help="How many anonymized text samples to dump for review")
    return p.parse_args()


def discover(root: Path) -> list[Path]:
    """Walk root, return list of candidate paths (docx/pdf/doc/xlsx)."""
    out: list[Path] = []
    supported = SUPPORTED_DIRECT | SUPPORTED_CONVERT
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in supported:
                out.append(Path(dirpath) / name)
    out.sort()
    return out


def convert_doc_to_docx(doc_path: Path, tmpdir: Path) -> Path | None:
    """Run libreoffice headless to convert .doc → .docx in tmpdir."""
    if not shutil.which("libreoffice") and not shutil.which("soffice"):
        return None
    cmd = [
        shutil.which("libreoffice") or shutil.which("soffice"),
        "--headless", "--convert-to", "docx", "--outdir", str(tmpdir), str(doc_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    out = tmpdir / (doc_path.stem + ".docx")
    return out if out.exists() else None


async def worker(
    sem: asyncio.Semaphore,
    pipeline: IngestPipeline,
    path: Path,
    tmpdir: Path,
    dry_run: bool,
) -> IngestResult:
    async with sem:
        target = path
        if path.suffix.lower() == ".doc":
            converted = convert_doc_to_docx(path, tmpdir)
            if converted is None:
                return IngestResult(
                    source_path=path, success=False,
                    skipped_reason="skipped_no_libreoffice",
                )
            target = converted
        if dry_run:
            # Run pipeline up to anonymization but skip the Qdrant upsert.
            # Re-using the pipeline keeps anonymization output consistent.
            # We monkeypatch the rag.index_document on a per-call basis below.
            original = pipeline.rag.index_document
            pipeline.rag.index_document = _noop_index  # type: ignore[assignment]
            try:
                return await pipeline.process(target)
            finally:
                pipeline.rag.index_document = original  # type: ignore[assignment]
        return await pipeline.process(target)


async def _noop_index(**kwargs):
    return 0  # dry-run: just return "0 chunks indexed"


def write_manifest_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "source_path", "success", "skipped_reason", "fingerprint",
            "chunks_indexed", "year", "modules", "doc_type", "size_band", "error",
        ])


def append_manifest(path: Path, r: IngestResult) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        meta = r.metadata or {}
        w.writerow([
            str(r.source_path), r.success, r.skipped_reason or "",
            r.fingerprint or "", r.chunks_indexed,
            meta.get("year", ""), ",".join(meta.get("modules", []) or []),
            meta.get("doc_type", ""), meta.get("size_band", ""),
            (r.error or "")[:300],
        ])


def sample_for_review(samples_dir: Path, target_count: int, results: list[IngestResult]) -> None:
    """Pick random successful results, re-read their anonymized text from
    the pipeline's last output (we don't keep it in memory by design;
    user re-runs with smaller sample for inspection).

    For now this is a stub — the sampling logic at scale needs to dump
    chunk previews from Qdrant. The CLI flag is kept so the spot-check
    workflow has an obvious entry point.
    """
    samples_dir.mkdir(parents=True, exist_ok=True)
    successes = [r for r in results if r.success]
    if not successes:
        return
    chosen = random.sample(successes, min(target_count, len(successes)))
    for r in chosen:
        manifest_line = (
            f"# source: {r.source_path}\n# fingerprint: {r.fingerprint}\n"
            f"# chunks: {r.chunks_indexed}\n# metadata: {asdict(r) if hasattr(r, '__dict__') else r}\n"
        )
        (samples_dir / f"{r.fingerprint}.txt").write_text(manifest_line, encoding="utf-8")


async def main() -> int:
    args = parse_args()
    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        return 2

    print(f"Scanning {root} for supported docs…")
    files = discover(root)
    if args.limit > 0:
        files = files[: args.limit]
    print(f"Found {len(files)} candidate documents.")

    rag = RAGService.from_settings()
    llm_reviewer = None if args.no_llm_review else LLMClient.from_settings()
    pipeline = IngestPipeline(rag=rag, llm_reviewer=llm_reviewer)

    write_manifest_header(MANIFEST_PATH)
    print(f"Manifest: {MANIFEST_PATH}")
    if args.dry_run:
        print("[dry-run] Anonimização rodará, NADA será enviado ao Qdrant.")

    sem = asyncio.Semaphore(args.workers)
    with tempfile.TemporaryDirectory(prefix="ps_ingest_") as tmp:
        tmpdir = Path(tmp)
        tasks = [worker(sem, pipeline, p, tmpdir, args.dry_run) for p in files]

        results: list[IngestResult] = []
        done = 0
        for coro in asyncio.as_completed(tasks):
            r = await coro
            results.append(r)
            append_manifest(MANIFEST_PATH, r)
            done += 1
            if done % 25 == 0 or done == len(tasks):
                ok = sum(1 for x in results if x.success)
                print(f"  [{done}/{len(tasks)}] success={ok} dup={sum(1 for x in results if x.skipped_reason=='duplicate')}")

    print("\n=== resumo ===")
    print(f"total processed: {len(results)}")
    print(f"  success      : {sum(1 for r in results if r.success)}")
    print(f"  duplicates   : {sum(1 for r in results if r.skipped_reason == 'duplicate')}")
    print(f"  empty/unsupp : {sum(1 for r in results if r.skipped_reason in ('empty_text','unsupported_format'))}")
    print(f"  no_libreoff  : {sum(1 for r in results if r.skipped_reason == 'skipped_no_libreoffice')}")
    print(f"  errors       : {sum(1 for r in results if r.error)}")
    print(f"manifest: {MANIFEST_PATH}")

    if args.samples > 0:
        sample_for_review(SAMPLES_DIR, args.samples, results)
        print(f"samples: {SAMPLES_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
