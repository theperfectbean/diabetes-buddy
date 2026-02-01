# Enhanced Knowledge Base Setup

This guide explains how to set up the enhanced Diabetes Buddy knowledge base with full-text ADA Standards of Care PDFs for the most authoritative clinical recommendations.

## Overview

Diabetes Buddy ships with automated ingestion of ADA Standards abstracts (zero user action required). For enhanced clinical detail, you can optionally download and ingest the full-text PDFs.

## Quick Setup

### 1. Download ADA Standards PDFs

```bash
python scripts/download_ada_helper.py
```

This interactive script will:
- Display direct links to all 17 ADA Standards sections
- Guide you through downloading each PDF from diabetesjournals.org
- Verify files are saved correctly
- Expected location: `data/knowledge/ada_standards_pdfs/`

### 2. Ingest PDFs

After downloading, run:

```bash
python scripts/ingest_ada_standards.py
```

The script automatically detects PDFs and ingests them alongside existing abstracts.

### 3. Verify Status

Check your knowledge base status:

```bash
python scripts/check_knowledge_status.py
```

You should see something like:
```
✅ ADA Standards 2026: 19 chunks (abstracts only) ⚠️ Full-text available - run: python scripts/download_ada_helper.py
```

After PDF ingestion:
```
✅ ADA Standards 2026: 450 chunks (19 abstracts + 431 PDF)
```

## PDF Details

### File Format
- **Format**: PDF
- **Naming**: `section_XX_title.pdf` (e.g., `section_06_glycemic_goals.pdf`)
- **Source**: diabetesjournals.org/care/issue/49/Supplement_1

### Expected File Sizes
- Introduction/Summary: ~50-100KB
- Major sections (6, 9, 10): ~200-400KB
- All others: ~100-200KB
- **Total**: ~2-3MB for all 17 sections

### Validation Checksums
Each PDF contains ADA copyright notices and can be validated by checking the section headers match the expected titles.

## Annual Updates

ADA Standards are published annually in January. When new Standards are released:

1. **Automatic**: PMC abstracts update automatically via monthly cron job
2. **Manual**: Download new PDFs using the helper script
3. **Reminder**: The status checker will notify you of available updates

## Troubleshooting

### PDF Ingestion Fails
**Symptoms**: PDFs detected but no chunks added
**Solutions**:
1. Verify PDFs are valid: `file data/knowledge/ada_standards_pdfs/*.pdf`
2. Check permissions: `ls -la data/knowledge/ada_standards_pdfs/`
3. Re-run ingestion: `python scripts/ingest_ada_standards.py --pdf-only`

### Download Issues
**Symptoms**: Cannot access diabetesjournals.org
**Solutions**:
1. Use a different browser or VPN if needed
2. PDFs may require institutional access - check with your healthcare provider
3. Abstracts remain available even without PDFs

### Storage Impact
- **Abstracts only**: ~50KB ChromaDB storage
- **With PDFs**: ~5-10MB additional ChromaDB storage
- PDFs themselves: ~2-3MB on disk

## Legal & Compliance

### Copyright Notice
- ADA Standards of Care © American Diabetes Association
- PDFs provided for personal educational use only
- Do not redistribute or use commercially
- Abstracts via PMC are public domain

### Data Privacy
- No user health data is transmitted
- All processing happens locally
- PDFs are stored in `data/knowledge/ada_standards_pdfs/` (git-ignored)

## Technical Details

### Collection Structure
- **Collection**: `ada_standards`
- **Abstract chunks**: `source_type: "abstract"` or `"full_text"`
- **PDF chunks**: `source_type: "full_text_pdf"`
- **Metadata**: Section number, topic, confidence=1.0

### Query Enhancement
With PDFs, queries like "HbA1c targets" return more detailed clinical recommendations including:
- Specific target ranges by age group
- Evidence levels for recommendations
- Implementation considerations
- References to supporting studies

### Performance Impact
- PDF ingestion: ~2-3 minutes one-time setup
- Query time: No change (<5s)
- Memory usage: ~50MB additional for PDF chunks

## Comparison: Abstracts vs Full-Text

| Feature | Abstracts Only | With PDFs |
|---------|----------------|-----------|
| **Setup** | Automatic | 15-30 min manual |
| **Chunks** | ~19 | ~400-500 |
| **Detail Level** | Summary | Full recommendations |
| **Evidence** | Citations only | Complete references |
| **Updates** | Monthly auto | Annual manual |
| **Storage** | ~50KB | ~10MB |
| **Legal** | Public domain | Personal use only |

## Integration with Auto-Updates

The monthly update pipeline (`scripts/monthly_update.py`) will:
1. Update PMC abstracts automatically
2. Check for new ADA Standards annually
3. Notify if PDF updates are available
4. Not overwrite user-provided PDFs

For full automation, consider setting up a yearly reminder to download new Standards when published.