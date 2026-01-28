"""
Diabetes Buddy CLI - Interactive query interface.

Usage:
    python -m diabuddy                     # Interactive REPL mode
    python -m diabuddy "your question"     # Single query mode
    python -m diabuddy --help              # Show help
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

from agents import TriageAgent, SafetyAuditor, Severity


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Severity colors
    GREEN = "\033[92m"      # INFO
    YELLOW = "\033[93m"     # WARNING
    RED = "\033[91m"        # BLOCKED

    # Other colors
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"


def colored(text: str, color: str, bold: bool = False) -> str:
    """Apply color to text if terminal supports it."""
    if not sys.stdout.isatty():
        return text
    prefix = Colors.BOLD if bold else ""
    return f"{prefix}{color}{text}{Colors.RESET}"


def severity_color(severity: Severity) -> str:
    """Get color for severity level."""
    return {
        Severity.INFO: Colors.GREEN,
        Severity.WARNING: Colors.YELLOW,
        Severity.BLOCKED: Colors.RED,
    }.get(severity, Colors.RESET)


def print_header():
    """Print the CLI header."""
    print(colored("=" * 60, Colors.CYAN))
    print(colored("  Diabetes Buddy - Agentic Knowledge Partner", Colors.CYAN, bold=True))
    print(colored("=" * 60, Colors.CYAN))
    print()
    print(colored("Commands:", Colors.DIM))
    print(colored("  /help    - Show this help", Colors.DIM))
    print(colored("  /audit   - Show audit summary", Colors.DIM))
    print(colored("  /sources - List knowledge sources", Colors.DIM))
    print(colored("  /quit    - Exit the program", Colors.DIM))
    print()


def print_sources():
    """Print available knowledge sources."""
    print(colored("\nKnowledge Sources:", Colors.BLUE, bold=True))
    sources = [
        ("Theory", "Think Like a Pancreas", "Diabetes management concepts, insulin strategies"),
        ("Algorithm", "CamAPS FX Manual", "Hybrid closed-loop settings, Boost/Ease modes"),
        ("Hardware", "Ypsomed Pump Manual", "Pump operation, cartridge changes"),
        ("CGM", "FreeStyle Libre 3 Manual", "Sensor application, readings, alarms"),
    ]
    for category, name, description in sources:
        print(f"  {colored(category, Colors.CYAN)}: {name}")
        print(f"    {colored(description, Colors.DIM)}")
    print()


def format_response(safe_response, verbose: bool = False) -> str:
    """Format a response for display."""
    lines = []
    audit = safe_response.audit
    triage = safe_response.triage_response

    # Classification info
    if triage:
        cat = triage.classification.category.value.upper()
        conf = f"{triage.classification.confidence:.0%}"
        lines.append(colored(f"[{cat}] ", Colors.CYAN) + colored(f"({conf} confidence)", Colors.DIM))

        if verbose and triage.classification.reasoning:
            lines.append(colored(f"  Reasoning: {triage.classification.reasoning}", Colors.DIM))

    # Safety status
    sev_color = severity_color(audit.max_severity)
    sev_text = audit.max_severity.value.upper()
    lines.append(colored(f"Safety: {sev_text}", sev_color))

    if audit.findings:
        for f in audit.findings:
            fc = severity_color(f.severity)
            lines.append(colored(f"  [{f.severity.value}] {f.category}: {f.reason}", fc))

    # Response
    lines.append("")
    lines.append(colored("-" * 60, Colors.DIM))
    lines.append(safe_response.response)

    return "\n".join(lines)


def run_query(auditor: SafetyAuditor, query: str, verbose: bool = False, as_json: bool = False):
    """Run a single query and display results."""
    try:
        print(colored("\nProcessing...", Colors.DIM))
        response = auditor.process(query, verbose=verbose)

        if as_json:
            output = {
                "query": query,
                "classification": {
                    "category": response.triage_response.classification.category.value,
                    "confidence": response.triage_response.classification.confidence,
                    "reasoning": response.triage_response.classification.reasoning,
                },
                "safety": {
                    "severity": response.audit.max_severity.value,
                    "findings": [
                        {
                            "severity": f.severity.value,
                            "category": f.category,
                            "reason": f.reason,
                        }
                        for f in response.audit.findings
                    ],
                    "modified": response.audit.was_modified,
                },
                "response": response.response,
            }
            print(json.dumps(output, indent=2))
        else:
            print(format_response(response, verbose=verbose))

    except KeyboardInterrupt:
        print(colored("\n\nQuery cancelled.", Colors.YELLOW))
    except Exception as e:
        print(colored(f"\nError: {e}", Colors.RED))
        if verbose:
            import traceback
            traceback.print_exc()


def interactive_mode(auditor: SafetyAuditor, verbose: bool = False):
    """Run interactive REPL mode."""
    print_header()

    while True:
        try:
            query = input(colored("\nYou: ", Colors.GREEN, bold=True)).strip()

            if not query:
                continue

            # Handle commands
            if query.startswith("/"):
                cmd = query.lower()
                if cmd in ("/quit", "/exit", "/q"):
                    break
                elif cmd == "/help":
                    print_header()
                elif cmd == "/sources":
                    print_sources()
                elif cmd == "/audit":
                    summary = auditor.get_audit_summary()
                    print(colored("\nAudit Summary:", Colors.BLUE, bold=True))
                    print(f"  Total queries: {summary.get('total', 0)}")
                    print(colored(f"  Blocked: {summary.get('blocked', 0)}", Colors.RED))
                    print(colored(f"  Warnings: {summary.get('warnings', 0)}", Colors.YELLOW))
                    print(colored(f"  Safe: {summary.get('info', 0)}", Colors.GREEN))
                else:
                    print(colored(f"Unknown command: {cmd}", Colors.YELLOW))
                    print(colored("Type /help for available commands", Colors.DIM))
                continue

            # Run query
            run_query(auditor, query, verbose=verbose)

        except KeyboardInterrupt:
            print(colored("\n\nUse /quit to exit.", Colors.YELLOW))
        except EOFError:
            break

    # Show final audit summary
    summary = auditor.get_audit_summary()
    if summary.get("total", 0) > 0:
        print(colored("\n\nSession Summary:", Colors.BLUE, bold=True))
        print(f"  Queries processed: {summary['total']}")
        print(colored(f"  Blocked: {summary.get('blocked', 0)}", Colors.RED))
        print(colored(f"  Warnings: {summary.get('warnings', 0)}", Colors.YELLOW))

    print(colored("\nGoodbye! Remember to consult your healthcare provider.", Colors.CYAN))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Diabetes Buddy - Agentic Knowledge Partner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m diabuddy                              # Interactive mode
  python -m diabuddy "How do I change my pump?"   # Single query
  python -m diabuddy --json "What is Ease-off?"   # JSON output
        """
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Question to ask (omit for interactive mode)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show verbose output with debug info"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format (for scripting)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="Diabetes Buddy v0.1.0"
    )

    args = parser.parse_args()

    # Initialize agents
    try:
        print(colored("Initializing agents...", Colors.DIM))
        triage = TriageAgent()
        auditor = SafetyAuditor(triage_agent=triage)
        print(colored("Ready!\n", Colors.GREEN))
    except ValueError as e:
        print(colored(f"Configuration error: {e}", Colors.RED))
        print("Make sure GEMINI_API_KEY is set in your .env file")
        sys.exit(1)
    except Exception as e:
        print(colored(f"Initialization error: {e}", Colors.RED))
        sys.exit(1)

    # Run in appropriate mode
    if args.query:
        # Single query mode
        run_query(auditor, args.query, verbose=args.verbose, as_json=args.json)
    else:
        # Interactive mode
        if args.json:
            print(colored("Warning: --json flag ignored in interactive mode", Colors.YELLOW))
        interactive_mode(auditor, verbose=args.verbose)


if __name__ == "__main__":
    main()
