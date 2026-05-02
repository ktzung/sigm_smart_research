"""Xuất CSV bài báo đã tải PDF. Chạy: python _export_csv.py"""
import csv
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:abc@localhost:5432/research_platform")

from app.core.database import SessionLocal
from app.models.topic import Topic
from app.models.paper import Paper

db = SessionLocal()

try:
    # ── Thống kê tổng quan ────────────────────────────────────────────────────
    topics      = db.query(Topic).order_by(Topic.id).all()
    all_papers  = db.query(Paper).order_by(Paper.topic_id, Paper.id).all()
    downloaded  = [p for p in all_papers if p.pdf_downloaded and p.pdf_path]

    print(f"Topics:          {len(topics)}")
    print(f"Tổng bài báo:    {len(all_papers)}")
    print(f"Đã tải PDF:      {len(downloaded)}")
    print()

    for t in topics:
        t_papers = [p for p in all_papers if p.topic_id == t.id]
        t_dl     = [p for p in t_papers   if p.pdf_downloaded and p.pdf_path]
        print(f"  Topic {t.id}: {t.title[:60]!r}  →  {len(t_papers)} bài, {len(t_dl)} PDF")

    print()

    if not all_papers:
        print("Không có bài báo nào trong DB. Hãy chạy pipeline trước.")
        sys.exit(0)

    topic_map = {t.id: t.title for t in topics}

    # ── File 1: tất cả bài báo ────────────────────────────────────────────────
    out_all = Path("storage/papers_all.csv")
    out_all.parent.mkdir(parents=True, exist_ok=True)

    with open(out_all, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow([
            "paper_id", "topic_id", "topic_title",
            "title", "authors", "year", "venue", "citation_count",
            "decision_label", "relevance_score", "decision_method",
            "source_api", "external_id", "url", "pdf_url",
            "pdf_downloaded", "pdf_path", "parsed",
            "abstract_preview",
        ])
        for p in all_papers:
            authors_raw = p.authors or []
            if authors_raw and isinstance(authors_raw[0], dict):
                authors_str = "; ".join(a.get("name", "") for a in authors_raw if a.get("name"))
            else:
                authors_str = "; ".join(str(a) for a in authors_raw)

            label  = p.decision.label            if p.decision else ""
            score  = p.decision.relevance_score  if p.decision else ""
            method = p.decision.method           if p.decision else ""
            abstract_preview = (p.abstract or "")[:120].replace("\n", " ")

            w.writerow([
                p.id,
                p.topic_id,
                topic_map.get(p.topic_id, ""),
                p.title,
                authors_str,
                p.year or "",
                p.venue or "",
                p.citation_count if p.citation_count is not None else "",
                label, score, method,
                p.source_api or "",
                p.external_id or "",
                p.url or "",
                p.pdf_url or "",
                "yes" if p.pdf_downloaded else "no",
                p.pdf_path or "",
                "yes" if p.parsed else "no",
                abstract_preview,
            ])

    print(f"✓ Xuất {len(all_papers)} bài  →  {out_all}")

    # ── File 2: chỉ bài đã tải PDF ───────────────────────────────────────────
    out_dl = Path("storage/papers_downloaded.csv")

    with open(out_dl, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow([
            "paper_id", "topic_id", "topic_title",
            "title", "authors", "year", "venue", "citation_count",
            "decision_label", "relevance_score",
            "source_api", "external_id", "url", "pdf_url",
            "pdf_path", "parsed",
            "abstract_preview",
        ])
        for p in downloaded:
            authors_raw = p.authors or []
            if authors_raw and isinstance(authors_raw[0], dict):
                authors_str = "; ".join(a.get("name", "") for a in authors_raw if a.get("name"))
            else:
                authors_str = "; ".join(str(a) for a in authors_raw)

            label = p.decision.label           if p.decision else ""
            score = p.decision.relevance_score if p.decision else ""
            abstract_preview = (p.abstract or "")[:120].replace("\n", " ")

            w.writerow([
                p.id,
                p.topic_id,
                topic_map.get(p.topic_id, ""),
                p.title,
                authors_str,
                p.year or "",
                p.venue or "",
                p.citation_count if p.citation_count is not None else "",
                label, score,
                p.source_api or "",
                p.external_id or "",
                p.url or "",
                p.pdf_url or "",
                p.pdf_path or "",
                "yes" if p.parsed else "no",
                abstract_preview,
            ])

    print(f"✓ Xuất {len(downloaded)} bài có PDF  →  {out_dl}")

    # ── File 3: một file riêng cho từng topic ─────────────────────────────────
    for t in topics:
        t_papers = [p for p in all_papers if p.topic_id == t.id]
        if not t_papers:
            continue

        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in t.title[:40]).strip()
        out_t = Path(f"storage/papers_topic{t.id}_{safe_title}.csv")

        with open(out_t, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow([
                "paper_id", "title", "authors", "year", "venue", "citation_count",
                "decision_label", "relevance_score", "decision_method",
                "source_api", "external_id", "url", "pdf_url",
                "pdf_downloaded", "pdf_path", "parsed",
                "abstract_preview",
            ])
            for p in t_papers:
                authors_raw = p.authors or []
                if authors_raw and isinstance(authors_raw[0], dict):
                    authors_str = "; ".join(a.get("name", "") for a in authors_raw if a.get("name"))
                else:
                    authors_str = "; ".join(str(a) for a in authors_raw)

                label  = p.decision.label            if p.decision else ""
                score  = p.decision.relevance_score  if p.decision else ""
                method = p.decision.method           if p.decision else ""
                abstract_preview = (p.abstract or "")[:120].replace("\n", " ")

                w.writerow([
                    p.id, p.title, authors_str,
                    p.year or "", p.venue or "",
                    p.citation_count if p.citation_count is not None else "",
                    label, score, method,
                    p.source_api or "", p.external_id or "",
                    p.url or "", p.pdf_url or "",
                    "yes" if p.pdf_downloaded else "no",
                    p.pdf_path or "",
                    "yes" if p.parsed else "no",
                    abstract_preview,
                ])

        print(f"✓ Topic {t.id}: {len(t_papers)} bài  →  {out_t}")

finally:
    db.close()
