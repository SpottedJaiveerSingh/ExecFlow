from datetime import date
from pathlib import Path
import sys
sys.path.append(str(Path('.').resolve()))
import agent

SIM_DATE = date(2026,9,22)

tests = [
    ("Please send the vendor list by Wednesday morning.", 'email'),
    ("Mumbai lease: Need confirmation — who is handling the Mumbai lease?", 'email'),
    ("Expense report attached.", 'email'),
]

for text, src in tests:
    print('\nTEXT:', text)
    sents = agent._simple_sentence_split(text)
    print('Sentences:', sents)
    for s in sents:
        is_commit = any(agent.re.search(p, s, agent.re.I) for p in [r"\bI will\b", r"\bI'll\b", r"\bI need to\b", r"\bI owe\b", r"\bwill send\b", r"\bwill have\b", r"\bplease send\b", r"\bcan you send\b", r"\bneed to get\b", r"\bremind me\b"])
        print('Sentence:', s)
        print('is_commit:', is_commit)
    print('heuristic_extract ->', agent._heuristic_extract(text, src))
