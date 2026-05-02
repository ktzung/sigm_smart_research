"""PDF download and parsing module."""
import logging
import re
from pathlib import Path
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.paper import Paper, PaperChunk

logger = logging.getLogger(__name__)

# Domains known to block bots or require auth - skip immediately
_SKIP_DOMAINS = {
    "link.springer.com", "dl.acm.org", "ieeexplore.ieee.org",
    "www.sciencedirect.com", "onlinelibrary.wiley.com",
    "www.tandfonline.com", "journals.sagepub.com",
}

SECTION_PATTERNS = {
    "abstract":     r"\babstract\b",
    "introduction": r"\b(1\.?\s*introduction|introduction)\b",
    "method":       r"\b(method|methodology|approach|proposed|framework)\b",
    "experiments":  r"\b(experiment|evaluation|results|performance)\b",
    "conclusion":   r"\b(conclusion|summary|future work)\b",
}


def _detect_section(text: str) -> str:
    text_lower = text.lower()[:100]
    for section, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, text_lower):
            return section
    return "body"


def _is_skippable_url(url: str) -> bool:
    """Return True for URLs that will likely block or timeout."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(skip in domain for skip in _SKIP_DOMAINS)
    except Exception:
        return False


def download_pdf(paper: Paper, db: Session) -> bool:
    """Attempt to download PDF. Returns True on success."""
    if paper.pdf_downloaded and paper.pdf_path:
        return True
    if not paper.pdf_url:
        return False

    url = paper.pdf_url

    # Skip known paywalled domains immediately
    if _is_skippable_url(url):
        logger.debug("Skipping paywalled URL for paper %d: %s", paper.id, url)
        return False

    # Organise PDFs by topic so storage/pdfs/ stays navigable
    pdf_dir = Path(settings.pdf_download_dir) / f"topic_{paper.topic_id}"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"paper_{paper.id}.pdf"

    try:
        # Short timeouts: connect=5s, read=15s - don't hang on slow servers
        timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        headers = {"User-Agent": "Mozilla/5.0 (research-bot; academic use)"}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            # Verify it's actually a PDF
            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type and not url.endswith(".pdf"):
                if len(resp.content) < 1000:
                    logger.debug("Not a PDF response for paper %d", paper.id)
                    return False
            pdf_path.write_bytes(resp.content)
        paper.pdf_downloaded = True
        paper.pdf_path = str(pdf_path)
        db.commit()
        logger.info("Downloaded PDF for paper %d (%d KB)", paper.id, len(resp.content) // 1024)
        return True
    except httpx.TimeoutException:
        logger.warning("PDF download timeout for paper %d: %s", paper.id, url[:60])
        return False
    except Exception as e:
        logger.warning("PDF download failed for paper %d: %s", paper.id, e)
        return False


def parse_pdf(paper: Paper, db: Session) -> list[PaperChunk]:
    """Parse PDF into chunks. Falls back to abstract-only if PDF unavailable."""
    for chunk in paper.chunks:
        db.delete(chunk)
    db.flush()

    chunks: list[PaperChunk] = []
    if paper.pdf_downloaded and paper.pdf_path:
        chunks = _parse_with_pymupdf(paper, db)

    if not chunks:
        chunks = _fallback_abstract_chunk(paper, db)

    paper.parsed = True
    db.commit()
    logger.info("Parsed paper %d into %d chunks", paper.id, len(chunks))
    return chunks


def _parse_with_pymupdf(paper: Paper, db: Session) -> list[PaperChunk]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(paper.pdf_path)
        chunks: list[PaperChunk] = []
        current_section = "body"
        chunk_index = 0

        for page_num, page in enumerate(doc):
            blocks = page.get_text("blocks")
            for block in blocks:
                text = block[4].strip()
                if len(text) < 20:
                    continue
                detected = _detect_section(text)
                if detected != "body":
                    current_section = detected
                chunk = PaperChunk(
                    paper_id=paper.id,
                    section=current_section,
                    chunk_index=chunk_index,
                    text=text[:2000].replace("\x00", ""),  # strip NUL chars for PostgreSQL
                    page_number=page_num + 1,
                )
                db.add(chunk)
                chunks.append(chunk)
                chunk_index += 1

        doc.close()
        return chunks
    except Exception as e:
        logger.warning("PyMuPDF parsing failed for paper %d: %s", paper.id, e)
        return []


def _fallback_abstract_chunk(paper: Paper, db: Session) -> list[PaperChunk]:
    text = (paper.abstract or paper.title or "").replace("\x00", "")
    chunk = PaperChunk(
        paper_id=paper.id,
        section="abstract",
        chunk_index=0,
        text=text,
        page_number=None,
    )
    db.add(chunk)
    return [chunk]


def ingest_paper(paper: Paper, db: Session) -> dict:
    downloaded = download_pdf(paper, db)
    chunks = parse_pdf(paper, db)
    # If only got abstract fallback and paper has S2 ID, try quick S2 enrich
    if len(chunks) <= 1 and not downloaded and paper.external_id and paper.source_api == "semantic_scholar":
        try:
            from app.services.fulltext_enrichment import _s2_batch_enrich, enrich_paper
            s2_data = _s2_batch_enrich([paper], db)
            if s2_data.get(paper.id):
                result = enrich_paper(paper, s2_data[paper.id], db)
                if result["chunks_after"] > 1:
                    chunks = paper.chunks  # refreshed by enrich_paper
        except Exception as e:
            logger.debug("Inline S2 enrich failed for paper %d: %s", paper.id, e)
    return {"downloaded": paper.pdf_downloaded, "chunks": len(paper.chunks)}
