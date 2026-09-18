from datetime import date
from pathlib import Path
import sys
sys.path.append(str(Path('.').resolve()))
from agent import extract_actions

SIM_DATE = date(2026,9,22)
text = "Finalize the budget today."
items = extract_actions(text, "voice", simulation_date=SIM_DATE)
print('extracted count:', len(items))
for it in items:
    print(it.model_dump())
