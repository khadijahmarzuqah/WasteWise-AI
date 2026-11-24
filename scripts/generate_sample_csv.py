"""Regenerate the SYNTHETIC sample CSVs in sample_data/ (dates are relative to today)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import sample_data as s  # noqa: E402

out = Path(__file__).resolve().parent.parent / "sample_data"
out.mkdir(exist_ok=True)
s.sample_inventory_csv().to_csv(out / "sample_inventory.csv", index=False)
s.sample_sales_csv().to_csv(out / "sample_sales.csv", index=False)
s.template_inventory_csv().to_csv(out / "inventory_template.csv", index=False)
s.template_sales_csv().to_csv(out / "sales_template.csv", index=False)
print("written to", out)
