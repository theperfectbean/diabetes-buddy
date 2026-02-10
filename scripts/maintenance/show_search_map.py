"""
Show the full search_map in search_multiple
"""
from agents.triage import TriageAgent
import inspect

triage = TriageAgent()
researcher = triage.researcher

source = inspect.getsource(researcher.search_multiple)
print(source)
