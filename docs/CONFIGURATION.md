# Diabetes Buddy Configuration Guide

This document describes all configuration options available in `config/hybrid_knowledge.yaml`.

## Configuration Structure

```yaml
rag_quality:
  min_chunks: 3
  min_confidence: 0.7
  min_sources: 2
  min_chunk_confidence: 0.35

parametric_usage:
  max_ratio: 0.7
  confidence_score: 0.6

safety:
  enhanced_check_threshold: 0.3

emergency_detection:
  enabled: true
  severity_thresholds:
    critical: 0.9
    high: 0.7
    medium: 0.5
  response_templates:
    critical: "⚠️ MEDICAL EMERGENCY detected..."
    high: "⚠️ URGENT MEDICAL ATTENTION needed..."
    medium: "⚠️ MEDICAL ATTENTION recommended..."

logging:
  level: "INFO"
  file_path: "logs/hybrid_system.log"
  max_size_mb: 10
  backup_count: 5

knowledge_monitoring:
  staleness_threshold_days: 30
  critical_threshold_days: 90
```

## Section Details

### RAG Quality (`rag_quality`)
Controls the quality thresholds for RAG (Retrieval-Augmented Generation) retrieval.

- `min_chunks` (int, >=1): Minimum number of retrieved chunks required for "sufficient" coverage
- `min_confidence` (float, 0.0-1.0): Minimum average confidence score for sufficient coverage
- `min_sources` (int, >=1): Minimum number of unique sources required for sufficient coverage
- `min_chunk_confidence` (float, 0.0-1.0): Minimum confidence threshold for individual chunks to be included

### Parametric Usage (`parametric_usage`)
Controls fallback to parametric (LLM general) knowledge when RAG coverage is insufficient.

- `max_ratio` (float, 0.0-1.0): Maximum allowed ratio of parametric content before warning user
- `confidence_score` (float, 0.0-1.0): Fixed confidence score assigned to parametric knowledge

### Safety (`safety`)
Safety thresholds for enhanced checking.

- `enhanced_check_threshold` (float, 0.0-1.0): Threshold for triggering enhanced safety checks

### Emergency Detection (`emergency_detection`)
Medical emergency detection and response configuration.

- `enabled` (boolean): Whether emergency detection is active
- `severity_thresholds` (object): Score thresholds for severity levels
  - `critical` (float, 0.0-1.0): Score threshold for CRITICAL severity
  - `high` (float, 0.0-1.0): Score threshold for HIGH severity
  - `medium` (float, 0.0-1.0): Score threshold for MEDIUM severity
- `response_templates` (object): Response templates for different severity levels

### Logging (`logging`)
Logging configuration with file rotation.

- `level` (string): Log level - "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
- `file_path` (string): Path to log file
- `max_size_mb` (int, >=1): Maximum log file size in MB before rotation
- `backup_count` (int, >=1): Number of backup log files to keep

### Knowledge Monitoring (`knowledge_monitoring`)
Knowledge base freshness monitoring thresholds.

- `staleness_threshold_days` (int, >=1): Days after which knowledge is considered stale
- `critical_threshold_days` (int, >=1): Days after which knowledge is considered critically stale

## Validation Rules

The system validates all configuration values on startup:

- **Type checking**: Ensures correct data types
- **Range validation**: Checks numeric values are within valid ranges
- **Required fields**: Ensures all required sections and fields are present
- **File paths**: Validates writable log file paths

Invalid configurations will cause the application to fail startup with descriptive error messages.

## Environment-Specific Configuration

### Development
```yaml
logging:
  level: "DEBUG"
  max_size_mb: 50
  backup_count: 10

emergency_detection:
  enabled: false  # Disable in development
```

### Production
```yaml
logging:
  level: "INFO"
  max_size_mb: 100
  backup_count: 30

emergency_detection:
  enabled: true
```

### Testing
```yaml
rag_quality:
  min_chunks: 1  # Lower thresholds for testing
  min_confidence: 0.5

logging:
  level: "DEBUG"
```

## Hot Reload

Configuration changes require application restart. The system does not support hot reloading to ensure predictable behavior in production.

## Troubleshooting

### Common Validation Errors

1. **"rag_quality.min_chunks must be an integer >= 1"**
   - Ensure `min_chunks` is a positive integer

2. **"logging.level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"**
   - Use uppercase log level names

3. **"safety.enhanced_check_threshold must be a float between 0.0 and 1.0"**
   - Ensure threshold values are between 0.0 and 1.0

### Log File Issues

- Ensure the `logs/` directory exists and is writable
- Check file permissions for log rotation
- Monitor disk space for large log files

### Emergency Detection Tuning

- Start with higher severity thresholds in production
- Monitor false positives in emergency logs
- Adjust keyword lists based on real usage patterns