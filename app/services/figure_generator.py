"""
Figure generation for survey paper:
  1. PRISMA flow diagram
  2. Taxonomy tree/heatmap
  3. Year distribution bar chart
  4. Citation network (top papers)
  5. Label distribution pie chart
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _save(fig, path: Path, dpi: int = 150):
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    import matplotlib.pyplot as plt
    plt.close(fig)
    logger.info("Saved figure: %s", path)


def generate_prisma_flow(prisma_data: dict, out_dir: Path) -> Path:
    """PRISMA 2020 flow diagram as a clean box diagram."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    flow = prisma_data.get("prisma_flow", prisma_data)
    ident  = flow.get("identification", {})
    screen = flow.get("screening", {})
    incl   = flow.get("included", {})

    fig, ax = plt.subplots(figsize=(8, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")
    ax.set_facecolor("white")

    def box(x, y, w, h, text, color="#dbeafe", fontsize=9):
        rect = mpatches.FancyBboxPatch((x, y), w, h,
            boxstyle="round,pad=0.1", linewidth=1.2,
            edgecolor="#1e40af", facecolor=color)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2, text, ha="center", va="center",
                fontsize=fontsize, wrap=True,
                multialignment="center",
                bbox=dict(boxstyle="square,pad=0", fc="none", ec="none"))

    def arrow(x, y1, y2):
        ax.annotate("", xy=(x, y2), xytext=(x, y1),
                    arrowprops=dict(arrowstyle="->", color="#374151", lw=1.5))

    # Title
    ax.text(5, 11.5, "PRISMA 2020 Flow Diagram", ha="center", va="center",
            fontsize=12, fontweight="bold", color="#1e3a5f")

    # Identification
    box(1, 9.5, 8, 1.2,
        f"Records identified\n"
        f"Semantic Scholar + arXiv (n = {ident.get('records_identified', '?')})\n"
        f"Search queries: {ident.get('search_queries', '?')}",
        color="#dbeafe")
    arrow(5, 9.5, 8.5)

    # Screening
    box(1, 7.2, 8, 1.2,
        f"Records screened (n = {screen.get('records_screened', '?')})\n"
        f"Rule-based excluded: {screen.get('records_excluded_rule_based', 0)}\n"
        f"LLM-based excluded: {screen.get('records_excluded_llm', 0)}",
        color="#dcfce7")
    arrow(5, 7.2, 6.2)

    # Eligibility
    box(1, 4.9, 8, 1.2,
        f"Full-text assessed for eligibility\n"
        f"(n = {incl.get('studies_included', '?')})",
        color="#fef9c3")
    arrow(5, 4.9, 3.9)

    # Included breakdown
    box(1, 2.5, 8, 1.3,
        f"Studies included in synthesis (n = {incl.get('studies_included', '?')})\n"
        f"Direct: {incl.get('direct', 0)}  |  "
        f"Adjacent: {incl.get('adjacent', 0)}  |  "
        f"Foundational: {incl.get('foundational', 0)}",
        color="#f3e8ff")

    # Phase labels on left
    for y, label in [(10.0, "Identification"), (7.7, "Screening"),
                     (5.4, "Eligibility"), (3.1, "Included")]:
        ax.text(0.3, y, label, ha="center", va="center", fontsize=8,
                fontweight="bold", color="#6b7280", rotation=90)

    path = out_dir / "prisma_flow.pdf"
    _save(fig, path, dpi=200)
    return path


def generate_year_distribution(papers: list, out_dir: Path) -> Path:
    """Bar chart of papers per year."""
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    year_counts: dict[int, int] = {}
    for p in papers:
        if p.year and 2015 <= p.year <= 2026:
            year_counts[p.year] = year_counts.get(p.year, 0) + 1

    if not year_counts:
        return None

    years  = sorted(year_counts.keys())
    counts = [year_counts[y] for y in years]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(years, counts, color="#3b82f6", edgecolor="white", linewidth=0.5)
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_xlabel("Year", fontsize=10)
    ax.set_ylabel("Number of Papers", fontsize=10)
    ax.set_title("Publication Year Distribution of Included Papers", fontsize=11, fontweight="bold")
    ax.set_xticks(years)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)

    path = out_dir / "year_distribution.pdf"
    _save(fig, path)
    return path


def generate_label_distribution(papers: list, out_dir: Path) -> Path:
    """Pie chart of paper labels (direct/adjacent/foundational)."""
    import matplotlib.pyplot as plt

    counts = {"direct": 0, "adjacent": 0, "foundational": 0}
    for p in papers:
        if p.decision and p.decision.label in counts:
            counts[p.decision.label] += 1

    labels = [k.capitalize() for k, v in counts.items() if v > 0]
    sizes  = [v for v in counts.values() if v > 0]
    colors = ["#3b82f6", "#10b981", "#f59e0b"][:len(labels)]

    fig, ax = plt.subplots(figsize=(6, 5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct="%1.0f%%", startangle=90,
        wedgeprops=dict(edgecolor="white", linewidth=1.5),
    )
    for t in autotexts:
        t.set_fontsize(10)
    ax.set_title("Paper Classification Distribution", fontsize=11, fontweight="bold")

    path = out_dir / "label_distribution.pdf"
    _save(fig, path)
    return path


def generate_taxonomy_heatmap(taxonomy_data: dict, papers: list, out_dir: Path) -> Path:
    """Heatmap showing paper distribution across taxonomy dimensions."""
    import matplotlib.pyplot as plt
    import numpy as np

    dimensions = taxonomy_data.get("dimensions", {})
    paper_mapping = taxonomy_data.get("paper_mapping", {})

    if not dimensions or not paper_mapping:
        return None

    # Take first 2 dimensions for 2D heatmap
    dim_names = list(dimensions.keys())[:2]
    if len(dim_names) < 2:
        return None

    dim1_cats = dimensions[dim_names[0]]
    dim2_cats = dimensions[dim_names[1]]

    # Count papers per cell
    matrix = np.zeros((len(dim1_cats), len(dim2_cats)), dtype=int)
    for pid_str, mapping in paper_mapping.items():
        cat1 = mapping.get(dim_names[0])
        cat2 = mapping.get(dim_names[1])
        if cat1 in dim1_cats and cat2 in dim2_cats:
            i = dim1_cats.index(cat1)
            j = dim2_cats.index(cat2)
            matrix[i][j] += 1

    fig, ax = plt.subplots(figsize=(max(8, len(dim2_cats) * 1.5), max(5, len(dim1_cats) * 1.2)))
    im = ax.imshow(matrix, cmap="Blues", aspect="auto")

    ax.set_xticks(range(len(dim2_cats)))
    ax.set_yticks(range(len(dim1_cats)))
    ax.set_xticklabels(dim2_cats, rotation=30, ha="right", fontsize=8)
    ax.set_yticklabels(dim1_cats, fontsize=8)
    ax.set_xlabel(dim_names[1], fontsize=10, fontweight="bold")
    ax.set_ylabel(dim_names[0], fontsize=10, fontweight="bold")
    ax.set_title("Paper Distribution Across Taxonomy Dimensions", fontsize=11, fontweight="bold")

    # Annotate cells
    for i in range(len(dim1_cats)):
        for j in range(len(dim2_cats)):
            val = matrix[i][j]
            if val > 0:
                ax.text(j, i, str(val), ha="center", va="center",
                        fontsize=9, color="white" if val > matrix.max() * 0.6 else "black")

    plt.colorbar(im, ax=ax, label="Number of Papers")
    plt.tight_layout()

    path = out_dir / "taxonomy_heatmap.pdf"
    _save(fig, path)
    return path


def generate_top_cited(papers: list, out_dir: Path, top_n: int = 15) -> Path:
    """Horizontal bar chart of top cited papers."""
    import matplotlib.pyplot as plt

    cited = sorted(
        [p for p in papers if p.citation_count and p.citation_count > 0],
        key=lambda p: p.citation_count, reverse=True
    )[:top_n]

    if not cited:
        return None

    titles = [p.title[:45] + "…" if len(p.title) > 45 else p.title for p in cited]
    counts = [p.citation_count for p in cited]

    fig, ax = plt.subplots(figsize=(10, max(5, len(cited) * 0.5)))
    bars = ax.barh(range(len(titles)), counts, color="#6366f1", edgecolor="white")
    ax.set_yticks(range(len(titles)))
    ax.set_yticklabels(titles, fontsize=8)
    ax.set_xlabel("Citation Count", fontsize=10)
    ax.set_title(f"Top {len(cited)} Most Cited Papers in Corpus", fontsize=11, fontweight="bold")
    ax.bar_label(bars, padding=3, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.invert_yaxis()
    plt.tight_layout()

    path = out_dir / "top_cited.pdf"
    _save(fig, path)
    return path


def generate_all_figures(topic, taxonomy_data: dict | None, prisma_data: dict | None, out_dir: Path) -> dict[str, str]:
    """Generate all figures. Returns {name: filepath}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    generated = {}

    try:
        if prisma_data:
            p = generate_prisma_flow(prisma_data, out_dir)
            if p: generated["prisma_flow"] = str(p)
    except Exception as e:
        logger.warning("PRISMA figure failed: %s", e)

    try:
        p = generate_year_distribution(included, out_dir)
        if p: generated["year_distribution"] = str(p)
    except Exception as e:
        logger.warning("Year distribution figure failed: %s", e)

    try:
        p = generate_label_distribution(included, out_dir)
        if p: generated["label_distribution"] = str(p)
    except Exception as e:
        logger.warning("Label distribution figure failed: %s", e)

    try:
        if taxonomy_data:
            p = generate_taxonomy_heatmap(taxonomy_data, included, out_dir)
            if p: generated["taxonomy_heatmap"] = str(p)
    except Exception as e:
        logger.warning("Taxonomy heatmap failed: %s", e)

    try:
        p = generate_top_cited(included, out_dir)
        if p: generated["top_cited"] = str(p)
    except Exception as e:
        logger.warning("Top cited figure failed: %s", e)

    logger.info("Generated %d figures in %s", len(generated), out_dir)
    return generated
