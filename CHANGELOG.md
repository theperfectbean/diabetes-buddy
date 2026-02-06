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

