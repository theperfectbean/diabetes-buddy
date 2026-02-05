#!/usr/bin/env python3
"""
Groq Usage Monitor

Tracks daily token usage and costs across providers.
Reads logs from logs/ directory, aggregates stats, and reports usage.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.models import load_models_config  # We'll create this helper


def load_models_config() -> dict:
    """Load models.json configuration."""
    config_path = Path(__file__).parent.parent / "config" / "models.json"
    with open(config_path) as f:
        return json.load(f)


def find_log_files(logs_dir: Path) -> List[Path]:
    """Find all LLM usage log files."""
    log_files = []
    
    # Look for:
    # - llm_usage.log, llm_usage.*.log (rotated logs)
    # - unified_agent.log
    # - researcher.log
    patterns = [
        "llm_usage*.log*",
        "unified_agent*.log*",
        "researcher*.log*",
    ]
    
    for pattern in patterns:
        log_files.extend(logs_dir.glob(pattern))
    
    return sorted(set(log_files), reverse=True)


def parse_log_lines(log_file: Path) -> List[dict]:
    """Parse LLM usage entries from a log file."""
    entries = []
    
    try:
        with open(log_file) as f:
            for line in f:
                try:
                    # Try to extract JSON from log lines
                    # Format: "... LLM Usage [...]: {...json...}"
                    if "LLM Usage" in line or "llm_info" in line:
                        # Try to find JSON in the line
                        start_idx = line.find('{')
                        end_idx = line.rfind('}')
                        
                        if start_idx >= 0 and end_idx > start_idx:
                            json_str = line[start_idx:end_idx + 1]
                            entry = json.loads(json_str)
                            
                            # Extract timestamp if available
                            timestamp = line[:19]  # ISO format start
                            entry["timestamp"] = timestamp
                            
                            entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        logging.warning(f"Error parsing {log_file}: {e}")
    
    return entries


def aggregate_usage(
    entries: List[dict],
    models_config: dict,
    hours_back: int = 24,
) -> Dict[str, dict]:
    """
    Aggregate token usage by provider and model.
    
    Args:
        entries: Parsed log entries
        models_config: Configuration from models.json
        hours_back: Only include logs from last N hours
        
    Returns:
        Dict mapping provider/model to {tokens, cost, count}
    """
    cutoff = datetime.now() - timedelta(hours=hours_back)
    usage = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "request_count": 0,
    })
    
    groq_config = models_config.get("models", {}).get("groq", {})
    
    for entry in entries:
        try:
            # Parse timestamp
            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
            except:
                ts = datetime.now()
            
            # Skip if outside time window
            if ts < cutoff:
                continue
            
            # Extract provider and model
            provider = entry.get("provider") or entry.get("llm_provider", "unknown")
            model = entry.get("model") or entry.get("llm_model", "unknown")
            
            key = f"{provider}/{model}"
            
            # Extract token counts
            input_tokens = entry.get("input_tokens", 0)
            output_tokens = entry.get("output_tokens", 0)
            
            # Handle nested usage structure
            if isinstance(input_tokens, dict):
                input_tokens = input_tokens.get("input", 0)
            if isinstance(output_tokens, dict):
                output_tokens = output_tokens.get("output", 0)
            
            # Aggregate
            usage[key]["input_tokens"] += int(input_tokens or 0)
            usage[key]["output_tokens"] += int(output_tokens or 0)
            usage[key]["request_count"] += 1
            
            # Calculate cost if Groq
            if provider.lower() == "groq":
                model_short = model.split("/")[-1] if "/" in model else model
                model_cfg = groq_config.get(model_short, {})
                
                input_cost = model_cfg.get("cost_per_million_input_tokens", 0)
                output_cost = model_cfg.get("cost_per_million_output_tokens", 0)
                
                cost = (input_tokens / 1_000_000) * input_cost + \
                       (output_tokens / 1_000_000) * output_cost
                usage[key]["cost"] += cost
                
        except Exception as e:
            logging.warning(f"Error processing entry: {e}")
            continue
    
    return dict(usage)


def calculate_groq_rate_limit_status(total_tokens: int, tpd_limit: int = 200000) -> Tuple[float, str]:
    """
    Calculate Groq rate limit status.
    
    Args:
        total_tokens: Total tokens used today
        tpd_limit: Daily limit (default 200K)
        
    Returns:
        (percentage_used, status_string)
    """
    percentage = (total_tokens / tpd_limit) * 100
    
    if percentage < 25:
        status = "✅ Low usage"
    elif percentage < 50:
        status = "⚠️  Moderate usage"
    elif percentage < 75:
        status = "⚠️⚠️ High usage"
    else:
        status = "🔴 Critical - approaching limit"
    
    return percentage, status


def generate_report(usage: Dict[str, dict], models_config: dict) -> str:
    """Generate human-readable usage report."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    
    report_lines = [
        "=" * 70,
        f"LLM USAGE REPORT - {date_str}",
        "=" * 70,
        "",
    ]
    
    if not usage:
        report_lines.append("No usage data found in logs.")
        return "\n".join(report_lines)
    
    # Group by provider
    by_provider = defaultdict(dict)
    total_cost = 0.0
    total_input = 0
    total_output = 0
    
    for key, stats in sorted(usage.items()):
        provider, model = key.split("/", 1)
        by_provider[provider][model] = stats
        total_cost += stats["cost"]
        total_input += stats["input_tokens"]
        total_output += stats["output_tokens"]
    
    # Print by provider
    for provider in sorted(by_provider.keys()):
        models = by_provider[provider]
        provider_tokens = sum(m["input_tokens"] + m["output_tokens"] for m in models.values())
        provider_cost = sum(m["cost"] for m in models.values())
        
        report_lines.append(f"\n{provider.upper()}")
        report_lines.append("-" * 70)
        
        for model in sorted(models.keys()):
            stats = models[model]
            input_k = stats["input_tokens"] / 1000
            output_k = stats["output_tokens"] / 1000
            total_k = input_k + output_k
            
            line = (
                f"  {model:30s} │ "
                f"Input: {input_k:8.1f}K │ "
                f"Output: {output_k:8.1f}K │ "
                f"Total: {total_k:8.1f}K │ "
                f"Cost: ${stats['cost']:7.3f} │ "
                f"Reqs: {stats['request_count']:4d}"
            )
            report_lines.append(line)
        
        # Provider subtotal
        report_lines.append(f"  {provider.upper()} SUBTOTAL: {provider_tokens/1000:.1f}K tokens, ${provider_cost:.3f}")
    
    # Grand total
    report_lines.extend([
        "",
        "=" * 70,
        f"TOTAL: {total_input/1000:.1f}K input + {total_output/1000:.1f}K output = {(total_input+total_output)/1000:.1f}K tokens",
        f"TOTAL COST: ${total_cost:.3f}",
        "=" * 70,
    ])
    
    # Groq rate limit status
    if "groq" in by_provider:
        groq_tokens = sum(
            m["input_tokens"] + m["output_tokens"]
            for m in by_provider["groq"].values()
        )
        percentage, status = calculate_groq_rate_limit_status(groq_tokens)
        report_lines.extend([
            "",
            f"GROQ RATE LIMIT STATUS:",
            f"  {groq_tokens:,} / 200,000 tokens ({percentage:.1f}%) - {status}",
        ])
    
    # Cost comparison (if multiple providers used)
    if len(by_provider) > 1:
        report_lines.extend([
            "",
            "COST COMPARISON:",
        ])
        for provider in sorted(by_provider.keys()):
            provider_cost = sum(m["cost"] for m in by_provider[provider].values())
            report_lines.append(f"  {provider}: ${provider_cost:.3f}")
    
    return "\n".join(report_lines)


def save_json_report(usage: Dict[str, dict], output_file: Path) -> None:
    """Save usage report as JSON."""
    report = {
        "date": datetime.now().isoformat(),
        "usage_by_model": usage,
        "summary": {
            "total_cost": sum(s["cost"] for s in usage.values()),
            "total_input_tokens": sum(s["input_tokens"] for s in usage.values()),
            "total_output_tokens": sum(s["output_tokens"] for s in usage.values()),
            "total_requests": sum(s["request_count"] for s in usage.values()),
        }
    }
    
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"📊 JSON report saved to {output_file}")


def main():
    """Main monitoring script."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Paths
    repo_root = Path(__file__).parent.parent
    logs_dir = repo_root / "logs"
    
    if not logs_dir.exists():
        print(f"❌ Logs directory not found: {logs_dir}")
        sys.exit(1)
    
    print(f"📂 Scanning logs directory: {logs_dir}")
    
    # Load config
    try:
        models_config = load_models_config()
    except Exception as e:
        print(f"❌ Error loading models.json: {e}")
        sys.exit(1)
    
    # Find and parse logs
    log_files = find_log_files(logs_dir)
    if not log_files:
        print("⚠️  No log files found")
        return
    
    print(f"📄 Found {len(log_files)} log files")
    
    all_entries = []
    for log_file in log_files:
        entries = parse_log_lines(log_file)
        if entries:
            all_entries.extend(entries)
            print(f"  ✓ {log_file.name}: {len(entries)} entries")
    
    if not all_entries:
        print("⚠️  No usage data found in logs")
        return
    
    # Aggregate usage
    print(f"\n📊 Aggregating {len(all_entries)} usage entries...")
    usage = aggregate_usage(all_entries, models_config, hours_back=24)
    
    # Generate and print report
    report = generate_report(usage, models_config)
    print("\n" + report)
    
    # Save JSON report
    output_file = logs_dir / f"usage_{datetime.now().strftime('%Y-%m-%d')}.json"
    save_json_report(usage, output_file)


if __name__ == "__main__":
    main()
