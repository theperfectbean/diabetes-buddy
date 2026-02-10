"""
Check what search methods the researcher has for user sources
"""
from agents.triage import TriageAgent
import inspect

triage = TriageAgent()
researcher = triage.researcher

print("="*60)
print("RESEARCHER SEARCH METHODS")
print("="*60)
for method_name in dir(researcher):
    if 'search' in method_name.lower() and not method_name.startswith('_'):
        method = getattr(researcher, method_name)
        if callable(method):
            sig = inspect.signature(method)
            print(f"\n{method_name}{sig}")
            # Get docstring if available
            doc = inspect.getdoc(method)
            if doc:
                print(f"  → {doc.split(chr(10))[0][:80]}")

print("\n" + "="*60)
print("CHECK: Does researcher have search_user_sources?")
print("="*60)
print(f"Has 'search_user_sources': {hasattr(researcher, 'search_user_sources')}")

print("\n" + "="*60)
print("CHECK: What does search_multiple expect?")
print("="*60)
if hasattr(researcher, 'search_multiple'):
    source = inspect.getsource(researcher.search_multiple)
    print(source[:600])
