# Next: Build RAG Researcher Agent

Give this prompt to Claude Code:

---

Build a RAG (Retrieval-Augmented Generation) Researcher Agent that:

1. Uses the google-genai SDK to read and search our PDF knowledge base
2. Implements semantic search using Gemini embeddings
3. Has specialist methods for each knowledge domain:
   - search_theory() -> Think Like a Pancreas
   - search_camaps() -> CamAPS FX algorithm manual
   - search_ypsomed() -> Ypsomed pump hardware manual
   - search_libre() -> FreeStyle Libre 3 CGM manual

4. Returns exact quotes with page numbers and confidence scores
5. Uses the File API to upload PDFs to Gemini for processing
6. Stores file handles in a local cache to avoid re-uploading

Requirements:
- Save as agents/researcher.py
- Use google.generativeai for embeddings and file operations
- Load API key from environment variable GEMINI_API_KEY
- Include error handling for missing files and API failures
- Add a simple test in __main__ that searches all four knowledge sources

File locations are:
- docs/theory/Think-Like-a-Pancreas*.pdf
- docs/manuals/algorithm/user_manual_fx_mmoll_commercial_ca.pdf
- docs/manuals/hardware/YPU_eIFU_REF_700009424_UK-en_V01.pdf
- docs/manuals/hardware/ART41641-001_rev-A-web.pdf
