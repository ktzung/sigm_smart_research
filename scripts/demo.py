#!/usr/bin/env python3
"""
Demo script: runs the full pipeline for 'Federated Learning under Concept Drift'.
Usage: python scripts/demo.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from app.core.logging import setup_logging
from app.core.database import init_db, SessionLocal
from app.models.topic import Topic
from app.pipelines.orchestrator import run_full_pipeline

setup_logging()
console = Console()


def main():
    init_db()
    db = SessionLocal()

    console.print(Panel.fit("[bold blue]Research Automation Platform - Demo Run[/bold blue]"))

    # Create demo topic
    topic = Topic(
        title="Federated Learning under Concept Drift",
        description=(
            "Survey of methods addressing concept drift in federated learning settings, "
            "including non-IID data, distribution shift, and continual adaptation."
        ),
        target_paper_type="survey",
        target_quality="Q1/Q2",
        literature_scarce=True,
        adjacent_fields=[
            "Federated Continual Learning",
            "Concept Drift in Data Streams",
            "Non-IID Federated Learning",
            "Domain Adaptation",
            "Distribution Shift",
        ],
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    console.print(f"[green]✓[/green] Created topic: [bold]{topic.title}[/bold] (id={topic.id})")

    # Run full pipeline
    console.print("\n[yellow]Running full pipeline...[/yellow]")
    runs = run_full_pipeline(topic, db)

    # Print results table
    table = Table(title="Pipeline Results")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Summary")

    for run in runs:
        status_style = "green" if run.status == "done" else "red"
        table.add_row(
            run.stage,
            f"[{status_style}]{run.status}[/{status_style}]",
            str(run.result_summary or run.error or ""),
        )
    console.print(table)

    # Print paper count
    db.refresh(topic)
    included = [p for p in topic.papers if p.decision and p.decision.label != "exclude"]
    console.print(f"\n[green]Papers discovered:[/green] {len(topic.papers)}")
    console.print(f"[green]Papers included:[/green] {len(included)}")

    # Export markdown
    from app.services.export import build_export_bundle, export_markdown
    bundle = build_export_bundle(topic, db)
    md = export_markdown(bundle)
    output_path = f"survey_output_{topic.id}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)
    console.print(f"\n[green]✓[/green] Exported to [bold]{output_path}[/bold]")

    db.close()
    console.print("\n[bold green]Demo complete.[/bold green]")


if __name__ == "__main__":
    main()
