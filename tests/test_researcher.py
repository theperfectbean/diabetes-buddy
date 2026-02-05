import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from agents.researcher_chromadb import ResearcherAgent

researcher = ResearcherAgent()

# Test specific OpenAPS terms
test_queries = [
    'OpenAPS algorithm',
    'oref0',
    'artificial pancreas',
    'DIY closed loop'
]

for query in test_queries:
    results = researcher.query_knowledge(query, top_k=2)
    print(f'\nQuery: "{query}" - Found {len(results)} results')
    for i, r in enumerate(results):
        print(f'  {i+1}: confidence={r.confidence:.2f}, source={r.source}')
        print(f'     {r.quote[:80]}...')