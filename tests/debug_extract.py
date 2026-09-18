from datetime import date
from pathlib import Path
import sys
sys.path.append(str(Path('.').resolve()))
from agent import extract_actions

SIM_DATE = date(2026,9,22)

cases = {
    'ownership_unclear': ("Mumbai lease: Need confirmation — who is handling the Mumbai lease?", 'email'),
    'deadline': ("Please send the vendor list by Wednesday morning.", 'email'),
    'completed': [("Expense report attached.", 'email'), ("Received Wed evening.", 'email')]
}

print('--- Ownership unclear ---')
items = extract_actions(cases['ownership_unclear'][0], cases['ownership_unclear'][1], simulation_date=SIM_DATE)
print('extracted count:', len(items))
for it in items:
    print(it.json())

print('\n--- Deadline case ---')
items = extract_actions(cases['deadline'][0], cases['deadline'][1], simulation_date=SIM_DATE)
print('extracted count:', len(items))
for it in items:
    print(it.json())

print('\n--- Completed case (each) ---')
for t,s in cases['completed']:
    items = extract_actions(t, s, simulation_date=SIM_DATE)
    print(f"text: {t} -> count={len(items)}")
    for it in items:
        print(it.json())
