"""
Show exactly how _search_categories maps categories to collections
"""
from agents.triage import TriageAgent
import inspect

triage = TriageAgent()

# Get the full source of _search_categories
print("="*60)
print("FULL _search_categories METHOD")
print("="*60)
source = inspect.getsource(triage._search_categories)
print(source)

# Also check the process method to see how it's called
print("\n" + "="*60)
print("HOW process() CALLS _search_categories")
print("="*60)
process_source = inspect.getsource(triage.process)
# Find the relevant part
lines = process_source.split('\n')
for i, line in enumerate(lines):
    if '_search_categories' in line or 'search' in line.lower():
        print(f"{i:3d}: {line}")
