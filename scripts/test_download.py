import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from pathlib import Path

# Simulate what the endpoint does
topic_id = 1
template = "IEEEtran"

# Check path resolution
pdf_path = Path(f"./storage/latex/topic_{topic_id}/{template}/main.pdf")
print(f"Relative path : {pdf_path}")
print(f"Absolute path : {pdf_path.resolve()}")
print(f"Exists        : {pdf_path.exists()}")
print(f"Size          : {pdf_path.stat().st_size // 1024} KB" if pdf_path.exists() else "NOT FOUND")

# Check view-pdf response
latex_base = Path(f"./storage/latex/topic_{topic_id}")
pdfs = []
if latex_base.exists():
    for tmpl_dir in sorted(latex_base.iterdir()):
        if not tmpl_dir.is_dir():
            continue
        pdf = tmpl_dir / "main.pdf"
        if pdf.exists():
            pdfs.append({
                "template": tmpl_dir.name,
                "pdf_size_kb": pdf.stat().st_size // 1024,
                "download_url": f"/api/v1/topics/{topic_id}/download-pdf?template={tmpl_dir.name}",
            })

print(f"\nview-pdf response: {pdfs}")
