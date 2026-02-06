## v0.2.2 - Architecture Audit Phase 1 & 2 (2026-02-06)

### Fixed
- [CRITICAL] User sources routing with metadata-based discovery
- [CRITICAL] Silent failure logging in search_multiple()
- [HIGH] Complete QueryCategory to source mapping with validation
- [HIGH] Standardized exception logging (print → logger)

### Added
- CHROMADB_PATH environment variable for custom storage location
- EMBEDDING_MODEL environment variable for model selection
- Module-level validation for category mappings

### Changed
- All search method exceptions now use logger.exception()
- CATEGORY_TO_SOURCE_MAP as single source of truth for routing


## v0.2.2 - Architecture Audit Phase 1 & 2 (2026-02-06)

### Fixed
- **[CRITICAL]** User sources routing with metadata-based discovery - queries now return device manual results
- **[CRITICAL]** Silent failure logging in search_multiple() - unmapped sources now logged with available options
- **[CRITICAL]** Debug script attribute bugs - fixed camelCase/snake_case mismatches
- **[HIGH]** Complete QueryCategory to source mapping - all 5 categories mapped with load-time validation
- **[HIGH]** Standardized exception logging - replaced 11 print() statements with logger

### Added
- `CHROMADB_PATH` environment variable for custom ChromaDB storage location
- `EMBEDDING_MODEL` environment variable for custom sentence transformer model
- Module-level `CATEGORY_TO_SOURCE_MAP` with validation for all query categories
- Load-time assertion that all QueryCategory values are mapped

### Changed
- All search method exceptions now use `logger.exception()` for proper error tracking
- ChromaDB path detection now respects environment override
- Embedding model selection supports both new and legacy environment variable names

### Performance
- End-to-end query: 17.74s (within acceptable range)
- USER_SOURCES queries: 10 results from device manuals
- No test regressions introduced

### Documentation
- Added CHROMADB_PATH and EMBEDDING_MODEL to README.md environment variables
- Documented backward compatibility for LOCAL_EMBEDDING_MODEL

### Audit Status
- Phase 1 (Critical): ✅ Complete (2 issues, 17 min)
- Phase 2 Quick Wins: ✅ Complete (4 issues, 70 min)
- Phase 2 Remaining: 2 issues (optional, 45 min)
- Phase 3 (Type Safety): 7 issues (~2 hours)
- Phase 4 (Testing): 4 issues (~2.5 hours)

**Total issues resolved:** 6 of 28 from audit
**Total time invested:** 87 minutes
**Impact:** All critical user-facing bugs fixed, foundation solidified
