"""
LaTeX export supporting major Q1 journal templates:
  - IEEEtran   : IEEE Transactions (TNNLS, TPAMI, TKDE, Access) - DEFAULT
  - acmart     : ACM Computing Surveys
  - elsarticle : Elsevier (Neural Networks, Pattern Recognition, NEUCOM)
  - svjour3    : Springer (Machine Learning, IJCV)

Also handles:
  - Author block generation per template
  - Abstract from stored topic.paper_abstract
  - Figure generation (PRISMA, year dist, taxonomy heatmap, top cited)
  - PDF compilation via pdflatex (MiKTeX/TeX Live)
"""
import logging
import re
import subprocess
import shutil
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.topic import Topic
from app.models.pipeline import DraftSection, TaxonomyCandidate, GapRecord

logger = logging.getLogger(__name__)

# ── Template definitions ──────────────────────────────────────────────────────
TEMPLATES = {
    "IEEEtran": {
        "docclass":    r"\documentclass[journal]{IEEEtran}",
        "packages":    [
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{cite}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{hyperref}",
            r"\usepackage{url}",
            r"\usepackage{multirow}",
            r"\usepackage{array}",
        ],
        "bibstyle":    "IEEEtran",
        "cite_cmd":    r"\cite",
        "title_block": lambda title, authors: (
            rf"\title{{{title}}}" + "\n"
            + rf"\author{{{authors}}}"
        ),
        "abstract_env": (r"\begin{abstract}", r"\end{abstract}"),
        "keywords_cmd": r"\begin{{IEEEkeywords}}{kw}\end{{IEEEkeywords}}",
        "note": "IEEE Transactions on Neural Networks and Learning Systems / TPAMI / TKDE",
    },
    "acmart": {
        "docclass":    r"\documentclass[acmsmall,review]{acmart}",
        "packages":    [
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{booktabs}",
            r"\usepackage{multirow}",
            r"\usepackage{amsmath}",
        ],
        "bibstyle":    "ACM-Reference-Format",
        "cite_cmd":    r"\cite",
        "title_block": lambda title, authors: (
            rf"\title{{{title}}}" + "\n"
            + r"\author{[Author Names]}" + "\n"
            + r"\affiliation{\institution{[Institution]}}"
        ),
        "abstract_env": (r"\begin{abstract}", r"\end{abstract}"),
        "keywords_cmd": r"\keywords{{{kw}}}",
        "note": "ACM Computing Surveys (CSUR)",
    },
    "elsarticle": {
        "docclass":    r"\documentclass[preprint,12pt]{elsarticle}",
        "packages":    [
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{hyperref}",
            r"\usepackage{multirow}",
            r"\usepackage{lineno}",
            r"\modulolinenumbers[5]",
        ],
        "bibstyle":    "elsarticle-num",
        "cite_cmd":    r"\cite",
        "title_block": lambda title, authors: (
            r"\begin{frontmatter}" + "\n"
            + rf"\title{{{title}}}" + "\n"
            + r"\author{[Author Names]}" + "\n"
            + r"\address{[Institution]}"
        ),
        "abstract_env": (r"\begin{abstract}", r"\end{abstract}" + "\n" + r"\end{frontmatter}"),
        "keywords_cmd": r"\begin{{keyword}}{kw}\end{{keyword}}",
        "note": "Elsevier: Neural Networks / Neurocomputing / Pattern Recognition",
    },
    "svjour3": {
        "docclass":    r"\documentclass[smallextended]{svjour3}",
        "packages":    [
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{hyperref}",
        ],
        "bibstyle":    "spbasic",
        "cite_cmd":    r"\cite",
        "title_block": lambda title, authors: (
            rf"\title{{{title}}}" + "\n"
            + r"\author{[Author Names]}" + "\n"
            + r"\institute{[Author Names] \at [Institution]}"
        ),
        "abstract_env": (r"\begin{abstract}", r"\end{abstract}"),
        "keywords_cmd": r"\keywords{{{kw}}}",
        "note": "Springer: Machine Learning / International Journal of Computer Vision",
    },
}

SECTION_ORDER = [
    "introduction", "background", "problem_formulation", "methodology",
    "taxonomy", "literature_review", "critical_analysis",
    "future_directions", "conclusion",
]

SECTION_TITLES = {
    "introduction":        "Introduction",
    "background":          "Background and Related Work",
    "problem_formulation": "Problem Formulation",
    "methodology":         "Methodology",
    "taxonomy":            "Taxonomy",
    "literature_review":   "Literature Review",
    "critical_analysis":   "Critical Analysis",
    "future_directions":   "Future Directions and Open Problems",
    "conclusion":          "Conclusion",
}


def _cite_to_latex(text: str, citation_map: dict) -> str:
    def replace_cite(m):
        pid = m.group(1)
        key = citation_map.get(str(pid), f"paper{pid}")
        return rf"\cite{{{key}}}"
    return re.sub(r"\[CITE:(\d+)\]", replace_cite, text)


def _build_bibtex(topic: Topic) -> tuple[str, dict[str, str]]:
    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    entries = []
    id_to_key: dict[str, str] = {}
    used_keys: set[str] = set()

    for paper in included:
        authors = paper.authors or []
        first_author_raw = (authors[0] if authors else "").strip()
        first_author = re.sub(r"[^a-zA-Z]", "", (first_author_raw.split()[-1] if first_author_raw.split() else "Unknown"))
        year = paper.year or 2024
        base_key = f"{first_author}{year}"
        key = base_key
        suffix = ord("a")
        while key in used_keys:
            key = f"{base_key}{chr(suffix)}"
            suffix += 1
        used_keys.add(key)
        id_to_key[str(paper.id)] = key

        venue = paper.venue or ""
        is_conf = any(kw in venue.lower() for kw in
                      ["conference", "workshop", "proceedings", "icml", "neurips",
                       "iclr", "cvpr", "iccv", "aaai", "ijcai", "acl", "emnlp"])
        entry_type = "inproceedings" if is_conf else "article"

        author_str = " and ".join(authors[:8])
        if len(authors) > 8:
            author_str += " and others"

        lines = [f"@{entry_type}{{{key},"]
        lines.append(f"  title     = {{{{{paper.title}}}}},")
        lines.append(f"  author    = {{{author_str}}},")
        lines.append(f"  year      = {{{year}}},")
        if venue:
            field = "booktitle" if is_conf else "journal"
            lines.append(f"  {field:<9} = {{{{{venue}}}}},")
        if paper.url:
            lines.append(f"  url       = {{{paper.url}}},")
        if paper.external_id and paper.source_api == "arxiv":
            lines.append(f"  eprint    = {{{paper.external_id}}},")
            lines.append(f"  archivePrefix = {{arXiv}},")
        lines.append("}")
        entries.append("\n".join(lines))

    return "\n\n".join(entries), id_to_key


def _build_taxonomy_table(taxonomy: TaxonomyCandidate | None) -> str:
    if not taxonomy or not taxonomy.dimensions:
        return ""
    dims = taxonomy.dimensions
    lines = [
        r"\begin{table}[!t]",
        r"\renewcommand{\arraystretch}{1.3}",
        r"\caption{Proposed Multi-Dimensional Taxonomy}",
        r"\label{tab:taxonomy}",
        r"\centering",
        r"\begin{tabular}{p{3cm}p{9cm}}",
        r"\toprule",
        r"\textbf{Dimension} & \textbf{Categories} \\",
        r"\midrule",
    ]
    for dim, cats in dims.items():
        cats_str = ", ".join(cats) if isinstance(cats, list) else str(cats)
        cats_str = cats_str.replace("&", r"\&")
        dim_escaped = dim.replace("_", r"\_").replace("&", r"\&")
        lines.append(f"\\textbf{{{dim_escaped}}} & {cats_str} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def _build_author_block(authors_info: list | None, template: str) -> str:
    """Generate template-specific author block from stored author info."""
    if not authors_info:
        return ""

    if template == "IEEEtran":
        parts = []
        for a in authors_info:
            name = a.get("name", "Author")
            affil = a.get("affiliation", "")
            email = a.get("email", "")
            corr = (r"\thanks{Corresponding author. Email: " + email + "}") if a.get("is_corresponding") and email else ""
            parts.append(
                rf"\IEEEauthorblockN{{{name}{corr}}}" + "\n"
                + rf"\IEEEauthorblockA{{{affil}}}"
            )
        return r"\author{" + "\n\\and\n".join(parts) + "}"

    elif template == "acmart":
        lines = []
        for a in authors_info:
            lines.append(rf"\author{{{a.get('name', 'Author')}}}")
            if a.get("email"):
                lines.append(rf"\email{{{a['email']}}}")
            if a.get("affiliation"):
                lines.append(rf"\affiliation{{\institution{{{a['affiliation']}}}}}")
            if a.get("orcid"):
                lines.append(rf"\orcid{{{a['orcid']}}}")
        return "\n".join(lines)

    elif template == "elsarticle":
        lines = []
        affils: dict[str, int] = {}
        for a in authors_info:
            affil = a.get("affiliation", "")
            if affil not in affils:
                affils[affil] = len(affils) + 1
            idx = affils[affil]
            corr = r"\corref{cor}" if a.get("is_corresponding") else ""
            lines.append(rf"\author[{idx}]{{{a.get('name', 'Author')}{corr}}}")
        for affil, idx in affils.items():
            lines.append(rf"\address[{idx}]{{{affil}}}")
        for a in authors_info:
            if a.get("is_corresponding") and a.get("email"):
                lines.append(rf"\cortext[cor]{{Corresponding author. Email: {a['email']}}}")
                break
        return "\n".join(lines)

    elif template == "svjour3":
        names = " \\and ".join(a.get("name", "Author") for a in authors_info)
        affils = list({a.get("affiliation", "") for a in authors_info if a.get("affiliation")})
        inst_lines = "\n".join(rf"\institute{{{a}}}" for a in affils)
        return rf"\author{{{names}}}" + "\n" + inst_lines

    return ""


def compile_pdf(tex_dir: Path) -> dict:
    """
    Compile main.tex to main.pdf.
    Standard 4-pass: pdflatex -> bibtex -> pdflatex -> pdflatex
    """
    pdflatex = shutil.which("pdflatex")
    bibtex   = shutil.which("bibtex")

    if not pdflatex:
        return {"success": False, "error": "pdflatex not found. Install MiKTeX or TeX Live."}

    def run(cmd: list[str], label: str) -> tuple[int, str]:
        try:
            result = subprocess.run(
                cmd, cwd=str(tex_dir),
                capture_output=True, text=True, timeout=120,
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return -1, f"{label} timed out"

    log = []
    try:
        # Pass 1 - generates .aux with citation keys
        rc, out = run([pdflatex, "-interaction=nonstopmode", "main.tex"], "pass1")
        log.append(f"pdflatex pass 1: rc={rc}")
        if rc not in (0, 1):
            errors = [l for l in out.splitlines() if l.startswith("!")]
            return {"success": False, "error": "\n".join(errors[:5]) or out[-300:], "log": "\n".join(log)}

        # BibTeX - reads .aux, writes .bbl
        if bibtex and (tex_dir / "references.bib").exists():
            rc_bib, out_bib = run([bibtex, "main"], "bibtex")
            log.append(f"bibtex: rc={rc_bib}")
            bbl = tex_dir / "main.bbl"
            if bbl.exists():
                log.append(f"main.bbl: {bbl.stat().st_size} bytes")

        # Pass 2 - resolves citations
        rc, out = run([pdflatex, "-interaction=nonstopmode", "main.tex"], "pass2")
        log.append(f"pdflatex pass 2: rc={rc}")

        # Pass 3 - resolves cross-references
        rc, out = run([pdflatex, "-interaction=nonstopmode", "main.tex"], "pass3")
        log.append(f"pdflatex pass 3: rc={rc}")

        pdf_path = tex_dir / "main.pdf"
        if pdf_path.exists():
            size_kb = pdf_path.stat().st_size // 1024
            logger.info("PDF compiled: %s (%d KB)", pdf_path, size_kb)
            return {"success": True, "pdf_path": str(pdf_path), "size_kb": size_kb, "log": "\n".join(log)}
        else:
            log_file = tex_dir / "main.log"
            last_error = ""
            if log_file.exists():
                log_text = log_file.read_text(encoding="utf-8", errors="ignore")
                error_lines = [l for l in log_text.splitlines() if l.startswith("!")]
                last_error = "\n".join(error_lines[:5])
            return {"success": False, "error": last_error or "PDF not produced", "log": "\n".join(log)}

    except Exception as e:
        return {"success": False, "error": str(e), "log": "\n".join(log)}


def export_latex(
    topic: Topic,
    output_dir: str,
    db: Session,
    template: str = "IEEEtran",
    compile_to_pdf: bool = True,
    generate_figures: bool = True,
) -> dict:
    """
    Generate journal-ready LaTeX package, figures, and optionally compile to PDF.

    Args:
        template:         IEEEtran | acmart | elsarticle | svjour3
        compile_to_pdf:   Run pdflatex to produce main.pdf
        generate_figures: Generate matplotlib figures
    """
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template '{template}'. Choose: {list(TEMPLATES.keys())}")

    tmpl = TEMPLATES[template]
    out  = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig_dir = out / "figures"

    bibtex_str, id_to_key = _build_bibtex(topic)

    # Latest draft per section
    all_drafts = db.query(DraftSection).filter_by(topic_id=topic.id).all()
    latest: dict[str, DraftSection] = {}
    for d in all_drafts:
        if d.section_name not in latest or d.version > latest[d.section_name].version:
            latest[d.section_name] = d

    taxonomy = (
        db.query(TaxonomyCandidate).filter_by(topic_id=topic.id)
        .order_by(TaxonomyCandidate.created_at.desc()).first()
    )

    # ── Generate figures ──────────────────────────────────────────────────────
    figures_generated = {}
    if generate_figures:
        from app.services.figure_generator import generate_all_figures
        included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
        excluded = [p for p in topic.papers if p.decision and p.decision.label == "exclude"]
        label_counts: dict[str, int] = {}
        for p in included:
            if p.decision:
                label_counts[p.decision.label] = label_counts.get(p.decision.label, 0) + 1
        prisma_data = {"prisma_flow": {
            "identification": {
                "records_identified": len(topic.papers),
                "search_queries": sum(len(qp.bundles) for qp in topic.query_plans),
            },
            "screening": {
                "records_screened": len(topic.papers),
                "records_excluded_rule_based": sum(1 for p in excluded if p.decision and p.decision.method == "rule"),
                "records_excluded_llm": sum(1 for p in excluded if p.decision and p.decision.method == "llm"),
            },
            "included": {"studies_included": len(included), **label_counts},
        }}
        taxonomy_data = (
            {"dimensions": taxonomy.dimensions, "paper_mapping": taxonomy.paper_mapping}
            if taxonomy else None
        )
        figures_generated = generate_all_figures(topic, taxonomy_data, prisma_data, fig_dir)

    safe_title = topic.title.replace("&", r"\&").replace("%", r"\%")

    # ── Build .tex ────────────────────────────────────────────────────────────
    author_block = _build_author_block(topic.authors_info, template)

    lines = [
        "% Generated by ChimCanhCut Research Platform",
        f"% Template: {template} — {tmpl['note']}",
        f"% Topic: {topic.title}",
        "",
        tmpl["docclass"],
        "",
    ]
    lines += tmpl["packages"]
    lines += [""]

    # Title + author block (before \begin{document})
    lines.append(tmpl["title_block"](safe_title, "[Author Names]"))
    lines.append("")
    if author_block:
        # Replace last line (which has placeholder author) with real block
        lines[-2] = tmpl["title_block"](safe_title, "")
        lines.append(author_block)
        lines.append("")

    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")

    # Abstract - use stored abstract or informative placeholder
    abs_open, abs_close = tmpl["abstract_env"]
    abstract_text = (topic.paper_abstract or "").strip()
    if not abstract_text:
        abstract_text = (
            "% TODO: Enter your abstract via the Paper Metadata panel in the UI.\n"
            "% Required: 150-250 words covering motivation, methodology, key findings, contributions."
        )
    lines += [abs_open, abstract_text, abs_close, ""]

    # Keywords
    keywords = (topic.paper_keywords or "Federated Learning, Concept Drift, Non-IID Data, Distribution Shift").replace("&", r"\&")
    kw_line = tmpl["keywords_cmd"].format(kw=keywords)
    lines += [kw_line, ""]

    # Sections
    for section_name in SECTION_ORDER:
        draft = latest.get(section_name)
        if not draft:
            continue
        title = SECTION_TITLES.get(section_name, section_name.replace("_", " ").title())
        lines.append(rf"\section{{{title}}}")
        lines.append(rf"\label{{sec:{section_name}}}")
        lines.append("")

        content = _cite_to_latex(draft.content, id_to_key)
        # Escape special chars but preserve \cite{} commands
        parts = re.split(r"(\\cite\{[^}]+\})", content)
        escaped = []
        for part in parts:
            if part.startswith(r"\cite"):
                escaped.append(part)
            else:
                part = part.replace("%", r"\%")
                part = part.replace("#", r"\#")
                part = part.replace("&", r"\&")
                escaped.append(part)
        lines.append("".join(escaped))
        lines.append("")

        # Insert taxonomy table after taxonomy section
        if section_name == "taxonomy":
            tax_table = _build_taxonomy_table(taxonomy)
            if tax_table:
                lines.append(tax_table)
                lines.append("")
            if "taxonomy_heatmap" in figures_generated:
                lines += [
                    r"\begin{figure}[!t]", r"\centering",
                    r"\includegraphics[width=\columnwidth]{figures/taxonomy_heatmap}",
                    r"\caption{Heatmap of paper distribution across taxonomy dimensions.}",
                    r"\label{fig:taxonomy_heatmap}", r"\end{figure}", "",
                ]

        if section_name == "introduction" and "year_distribution" in figures_generated:
            lines += [
                r"\begin{figure}[!t]", r"\centering",
                r"\includegraphics[width=\columnwidth]{figures/year_distribution}",
                r"\caption{Publication year distribution of included papers.}",
                r"\label{fig:year_dist}", r"\end{figure}", "",
            ]

        if section_name == "methodology" and "prisma_flow" in figures_generated:
            lines += [
                r"\begin{figure}[!t]", r"\centering",
                r"\includegraphics[width=0.85\columnwidth]{figures/prisma_flow}",
                r"\caption{PRISMA 2020 flow diagram of the systematic literature search.}",
                r"\label{fig:prisma}", r"\end{figure}", "",
            ]

        if section_name == "literature_review" and "top_cited" in figures_generated:
            lines += [
                r"\begin{figure}[!t]", r"\centering",
                r"\includegraphics[width=\columnwidth]{figures/top_cited}",
                r"\caption{Top cited papers in the survey corpus.}",
                r"\label{fig:top_cited}", r"\end{figure}", "",
            ]

    # Bibliography
    lines += [
        rf"\bibliographystyle{{{tmpl['bibstyle']}}}",
        r"\bibliography{references}",
        "",
        r"\end{document}",
    ]

    main_tex = "\n".join(lines)

    # Write files
    (out / "main.tex").write_text(main_tex, encoding="utf-8")
    (out / "references.bib").write_text(bibtex_str, encoding="utf-8")

    readme = f"""# LaTeX Package — {topic.title}

## Template
{template} — {tmpl['note']}

## Files
- `main.tex`       — Main manuscript
- `references.bib` — BibTeX bibliography ({len(id_to_key)} references)
- `figures/`       — Generated figures ({len(figures_generated)} files)

## Compilation
```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## TODO before submission
1. Fill in author names via Paper Metadata panel in the UI
2. Write final abstract (150-250 words) via Paper Metadata panel
3. Check journal word/page limits
4. Run grammar check

## Sections included
{chr(10).join(f'- {SECTION_TITLES.get(s, s)}' for s in SECTION_ORDER if s in latest)}

## Figures generated
{chr(10).join(f'- {k}' for k in figures_generated) if figures_generated else '- None'}
"""
    (out / "README.md").write_text(readme, encoding="utf-8")

    result = {
        "output_dir": output_dir,
        "template": template,
        "journal_target": tmpl["note"],
        "files": ["main.tex", "references.bib", "README.md"],
        "sections": len(latest),
        "references": len(id_to_key),
        "figures": list(figures_generated.keys()),
    }

    # ── Compile PDF ───────────────────────────────────────────────────────────
    if compile_to_pdf:
        logger.info("Compiling PDF with pdflatex...")
        pdf_result = compile_pdf(out)
        result["pdf_compiled"] = pdf_result.get("success", False)
        result["pdf_path"]     = pdf_result.get("pdf_path", "")
        result["pdf_size_kb"]  = pdf_result.get("size_kb", 0)
        if not pdf_result["success"]:
            logger.warning("PDF compilation failed: %s", pdf_result.get("error", ""))
            result["pdf_error"] = pdf_result.get("error", "")

    logger.info("LaTeX export: template=%s sections=%d refs=%d figures=%d pdf=%s",
                template, len(latest), len(id_to_key), len(figures_generated),
                result.get("pdf_path", "not compiled"))
    return result
