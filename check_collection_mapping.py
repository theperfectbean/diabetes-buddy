"""
Check how triage maps category names to ChromaDB collection names
"""
from agents.triage import TriageAgent
import chromadb

# 1. Check what collections actually exist in ChromaDB
client = chromadb.PersistentClient(path=".cache/chromadb")
actual_collections = [c.name for c in client.list_collections()]
print("="*60)
print("ACTUAL CHROMADB COLLECTIONS")
print("="*60)
for name in actual_collections:
    coll = client.get_collection(name)
    print(f"  - {name}: {coll.count()} chunks")

# 2. Check triage's researcher structure
print("\n" + "="*60)
print("TRIAGE → RESEARCHER STRUCTURE")
print("="*60)

triage = TriageAgent()
print(f"Triage has researcher: {hasattr(triage, 'researcher')}")

if hasattr(triage, 'researcher'):
    researcher = triage.researcher
    print(f"Researcher type: {type(researcher).__name__}")
    print(f"Researcher module: {type(researcher).__module__}")
    
    # Check for backend
    if hasattr(researcher, 'backend'):
        print(f"\nResearcher has backend: {type(researcher.backend).__name__}")
    
    # Look for search methods
    search_methods = [m for m in dir(researcher) if 'search' in m.lower() and not m.startswith('_')]
    print(f"\nSearch methods available: {search_methods}")

# 3. Trace what happens when searching 'user_sources'
print("\n" + "="*60)
print("TRACE: What happens with 'user_sources' category?")
print("="*60)

# Look at the search_categories method
import inspect
if hasattr(triage, 'search_categories'):
    source_code = inspect.getsource(triage.search_categories)
    # Find the part that maps categories to sources
    print("search_categories source code (first 800 chars):")
    print(source_code[:800])
    print("\n... (truncated)")

print("\n" + "="*60)
print("CRITICAL QUESTION:")
print("="*60)
print("When category='user_sources', which ChromaDB collection")
print("should be searched? camaps_fx? user_manual_fx_mmoll_commercial_ca?")
print("Or all user-uploaded PDFs?")
