import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.services.latex_export import TEMPLATES, export_latex
from app.core.database import SessionLocal
from app.models.topic import Topic

print("Available templates:")
for name, t in TEMPLATES.items():
    print(f"  {name:<12} -> {t['note']}")

db = SessionLocal()
topic = db.query(Topic).first()
if topic:
    result = export_latex(topic, "./storage/latex/test_v2", db,
                          template="IEEEtran",
                          compile_to_pdf=True,
                          generate_figures=True)
    print("\nExport result:")
    for k, v in result.items():
        print(f"  {k}: {v}")
db.close()
