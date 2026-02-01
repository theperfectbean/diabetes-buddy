#!/usr/bin/env python3
"""
Test scraper for the 2026 ADA Standards of Care (Volume 49, Supplement 1).

Usage:
  python scripts/test_ada_scraper.py
  python scripts/test_ada_scraper.py --dry-run
  python scripts/test_ada_scraper.py --section 7

This script will:
- Respect robots.txt
- Fetch the Supplement TOC page and extract up to 17 sections
- For each section extract recommendations, evidence grading, abstract, DOI, and key updates
- Save one markdown file per section under `docs/clinical-guidelines/ada-standards-2026/`
- Save a master JSON index file `ada-standards-2026-index.json`

Dependencies:
  beautifulsoup4, requests

Example scraped section (excerpt):

```json
{
  "section_number": 7,
  "title": "Diabetes Technology",
  "recommendations": [
    {
      "id": "Recommendation 7.15",
      "text": "Use CGM at diagnosis for people with type 1 diabetes...",
      "evidence": "A"
    }
  ],
  "abstract": "Continuous glucose monitoring (CGM) has...",
  "doi": "10.2337/dc26-S1-007",
  "key_updates": ["CGM recommended at diabetes onset (2026 Recommendation 7.15)"]
}
```

This file includes comprehensive docstrings and type hints.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://diabetesjournals.org/care/issue/49/Supplement_1"
OUTPUT_DIR = "docs/clinical-guidelines/ada-standards-2026"
LOG_PATH = "logs/ada_scraper.log"
INDEX_FILE = "ada-standards-2026-index.json"
USER_AGENT = "Diabetes-Buddy-Research-Bot/1.0 (Educational)"
SECTION_PRIORITY = [7, 9, 6, 10, 11, 14]


@dataclass
class Recommendation:
    id: str
    text: str
    evidence: Optional[str] = None


@dataclass
class SectionResult:
    section_number: int
    title: str
    url: str
    recommendations: List[Recommendation]
    abstract: Optional[str]
    doi: Optional[str]
    key_updates: List[str]


def setup_logging(log_path: str = LOG_PATH) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def is_allowed(base_page: str, user_agent: str = USER_AGENT) -> bool:
    """Check robots.txt for permission to crawl the given page.

    Returns True if allowed or robots.txt cannot be parsed.
    """
    try:
        parsed = urlparse(base_page)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        allowed = rp.can_fetch(user_agent, base_page)
        if not allowed:
            logging.warning("robots.txt disallows fetching %s for %s", base_page, user_agent)
        return allowed
    except Exception as exc:  # pragma: no cover - network dependent
        logging.warning("Could not parse robots.txt: %s", exc)
        return True


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60]


def fetch(session: requests.Session, url: str, timeout: int = 20) -> Optional[str]:
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logging.error("Failed to fetch %s: %s", url, exc)
        return None


def parse_toc(html: str, base: str = BASE_URL) -> List[Tuple[int, str, str]]:
    """Parse the supplement table of contents and return list of (section_number, title, url).

    This function attempts to be robust against markup changes.
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []  # type: List[Tuple[int,str,str]]

    # Strategy: find anchors that likely refer to section articles
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        # heuristic: article links often contain 'doi' or '/toc/' or '/article/'
        if any(x in href for x in ("/toc/", "/article/", "/doi/", "/content/")):
            # try to extract a leading section number from text
            m = re.search(r"Section\s*(\d{1,2})", text, re.IGNORECASE)
            if not m:
                m = re.search(r"^(\d{1,2})[:\.-]\s*(.+)$", text)
            if m:
                sec = int(m.group(1))
                title = text
                full = urljoin(base, href)
                links.append((sec, title, full))

    # Deduplicate by section number, prefer first occurrence
    seen = set()
    deduped: List[Tuple[int, str, str]] = []
    for sec, title, full in links:
        if sec in seen:
            continue
        seen.add(sec)
        deduped.append((sec, title, full))

    # If we didn't find anything by heuristics, try heading-based approach
    if not deduped:
        for h in soup.find_all(re.compile("^h[1-6]$")):
            text = h.get_text(" ", strip=True)
            m = re.search(r"Section\s*(\d{1,2})[:\.-]?\s*(.+)$", text, re.IGNORECASE)
            if m:
                sec = int(m.group(1))
                title = m.group(2)
                a = h.find_next("a", href=True)
                if a:
                    full = urljoin(base, a["href"])
                    deduped.append((sec, title, full))

    # Sort by section number
    deduped.sort(key=lambda x: x[0])
    return deduped


def extract_doi(soup: BeautifulSoup) -> Optional[str]:
    # meta tag
    meta = soup.find("meta", attrs={"name": "citation_doi"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    # anchors to doi.org
    a = soup.find("a", href=re.compile(r"doi\.org"))
    if a:
        m = re.search(r"10\.\d{4,9}/[\w./-]+", a["href"])
        if m:
            return m.group(0)
    # any DOI-like text
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"10\.\d{4,9}/[\w./-]+", txt)
    if m:
        return m.group(0)
    return None


def extract_abstract(soup: BeautifulSoup) -> Optional[str]:
    # Common patterns: div.abstract, section with heading 'Abstract'
    ab = soup.find(class_=re.compile("abstract", re.I))
    if ab:
        return ab.get_text("\n", strip=True)
    # heading-based
    for h in soup.find_all(re.compile("^h[1-6]$")):
        if re.search(r"abstract", h.get_text(), re.I):
            # collect following paragraphs
            texts = []
            for sib in h.find_next_siblings():
                if sib.name and sib.name.startswith("h"):
                    break
                if sib.name == "p":
                    texts.append(sib.get_text(strip=True))
            if texts:
                return "\n\n".join(texts)
    # fallback: first paragraph in article content
    p = soup.find("p")
    if p:
        return p.get_text(strip=True)
    return None


def extract_recommendations(soup: BeautifulSoup) -> List[Recommendation]:
    text = soup.get_text("\n", sep="\n", strip=True)
    recs: List[Recommendation] = []

    # Find all occurrences of 'Recommendation' with nearby text
    for m in re.finditer(r"(Recommendation[s]?)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE):
        start = m.start()
        # capture up to next two paragraphs (~1000 chars) after match
        snippet = text[start : start + 1200]
        # try to split by newline to get the recommendation line and following explanation
        lines = [l.strip() for l in snippet.splitlines() if l.strip()]
        if not lines:
            continue
        rec_id = f"Recommendation {m.group(2)}"
        # The first line likely contains the recommendation sentence
        rec_text = " ".join(lines[:3])
        # evidence grading search
        ev = None
        # typical forms: (A), Grade A, Level of Evidence: A
        ev_m = re.search(r"\b(Level of Evidence|Grade|Evidence)[:\s]*([A-E])\b", snippet, re.I)
        if ev_m:
            ev = ev_m.group(2).upper()
        else:
            ev_m2 = re.search(r"\(([A-E])\)", snippet)
            if ev_m2:
                ev = ev_m2.group(1).upper()

        recs.append(Recommendation(id=rec_id, text=rec_text, evidence=ev))

    # De-duplicate by id keeping first occurrence
    seen = set()
    uniq: List[Recommendation] = []
    for r in recs:
        if r.id in seen:
            continue
        seen.add(r.id)
        uniq.append(r)
    return uniq


def extract_key_updates(soup: BeautifulSoup) -> List[str]:
    txt = soup.get_text(" ", strip=True)
    updates = []
    # Search for mentions of 2025 or 'update' lines
    for m in re.finditer(r"(update|updated|changes|new).*?2025", txt, re.I):
        start = max(0, m.start() - 100)
        updates.append(txt[start : m.end() + 200][:300])
    # short heuristic matches
    for phrase in (
        "CGM recommended",
        "automated insulin delivery",
        "heart failure",
        "CKD",
        "behavioral health",
    ):
        if re.search(phrase, txt, re.I):
            updates.append(phrase)
    # dedupe
    return list(dict.fromkeys(updates))


def save_section_markdown(result: SectionResult, out_dir: str = OUTPUT_DIR) -> str:
    os.makedirs(out_dir, exist_ok=True)
    slug = slugify(result.title or f"section-{result.section_number}")
    filename = f"section-{result.section_number}-{slug}.md"
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Section {result.section_number}: {result.title}\n\n")
        if result.doi:
            fh.write(f"**DOI:** {result.doi}\n\n")
        if result.abstract:
            fh.write("## Abstract\n\n")
            fh.write(result.abstract + "\n\n")
        fh.write("## Recommendations\n\n")
        for r in result.recommendations:
            ev = f" (Evidence: {r.evidence})" if r.evidence else ""
            fh.write(f"- **{r.id}**: {r.text}{ev}\n")
        if result.key_updates:
            fh.write("\n## Key updates\n\n")
            for u in result.key_updates:
                fh.write(f"- {u}\n")
    logging.info("Saved section %s to %s", result.section_number, path)
    return path


def run_scraper(
    base_url: str = BASE_URL,
    sections_only: Optional[List[int]] = None,
    dry_run: bool = False,
) -> Dict[str, object]:
    """Main scraper orchestration.

    Returns an index dictionary that is also saved to disk.
    """
    setup_logging()
    logging.info("Starting ADA 2026 scraper for %s", base_url)

    if not is_allowed(base_url):
        logging.error("Crawling disallowed by robots.txt; exiting.")
        return {}

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    toc_html = fetch(session, base_url)
    if not toc_html:
        logging.error("Failed to fetch TOC page; aborting.")
        return {}

    toc = parse_toc(toc_html, base_url)
    logging.info("Found %d candidate TOC entries", len(toc))

    # If the page doesn't clearly enumerate 17, still proceed but log
    if len(toc) < 17:
        logging.warning("Expected 17 sections but found %d on TOC; continuing with heuristics", len(toc))

    results: List[SectionResult] = []
    errors: List[int] = []

    # Filter by requested sections if provided
    if sections_only:
        toc = [t for t in toc if t[0] in sections_only]

    total = len(toc)
    for idx, (sec_num, title, url) in enumerate(toc, start=1):
        logging.info("Scraping Section %d/%d: %s...", idx, total, title)
        if dry_run:
            logging.info("Dry-run enabled; skipping fetch for %s", url)
            continue

        html = fetch(session, url)
        if not html:
            logging.error("Could not fetch section %s", sec_num)
            errors.append(sec_num)
            continue

        soup = BeautifulSoup(html, "html.parser")
        doi = extract_doi(soup)
        abstract = extract_abstract(soup)
        recommendations = extract_recommendations(soup)
        key_updates = extract_key_updates(soup)

        result = SectionResult(
            section_number=sec_num,
            title=title,
            url=url,
            recommendations=recommendations,
            abstract=abstract,
            doi=doi,
            key_updates=key_updates,
        )

        try:
            save_section_markdown(result)
            results.append(result)
        except Exception as exc:
            logging.exception("Failed to save section %s: %s", sec_num, exc)
            errors.append(sec_num)

        # Rate limit between section requests
        time.sleep(2)

    # Build index
    index = {
        "publication_date": "2026-01-01",
        "version": "2026 Volume 49 Supplement 1",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": base_url,
        "sections_found": [asdict(r) for r in results],
        "errors": errors,
    }

    # Save index
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    idx_path = os.path.join(OUTPUT_DIR, INDEX_FILE)
    with open(idx_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
    logging.info("Wrote index to %s", idx_path)

    # Validation checks
    num_sections = len(results)
    num_recs = sum(len(r.recommendations) for r in results)
    num_recs_with_evidence = sum(
        1 for r in results for rec in r.recommendations if rec.evidence
    )

    logging.info("Sections parsed: %d", num_sections)
    logging.info("Total recommendations extracted: %d", num_recs)
    logging.info(
        "Recommendations with evidence grading: %d", num_recs_with_evidence
    )

    # Test validation rules
    validation = {
        "expected_sections": 17,
        "sections_found": num_sections,
        "min_recommendations": 50,
        "recommendations_found": num_recs,
        "recommendations_with_evidence": num_recs_with_evidence,
    }

    logging.info("Validation: %s", validation)

    # If validation fails, still return index but exit with non-zero to indicate test fail
    failures = []
    if num_sections != 17:
        failures.append(f"Expected 17 sections, found {num_sections}")
    if num_recs < 50:
        failures.append(f"Expected >=50 recommendations, found {num_recs}")
    if num_recs_with_evidence < 1:
        failures.append("No evidence gradings found on recommendations")

    if failures:
        logging.error("Validation failed: %s", failures)
        # Save partial results already done; return and indicate failure via exit code from CLI
        return {"index": index, "validation": validation, "failures": failures}

    return {"index": index, "validation": validation, "failures": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="ADA 2026 Standards scraper (test script)")
    parser.add_argument("--dry-run", action="store_true", help="Do not fetch section pages; just parse TOC")
    parser.add_argument(
        "--section",
        nargs="*",
        type=int,
        help="Only scrape the specified section numbers (e.g., --section 7 9)",
    )
    args = parser.parse_args()

    res = run_scraper(sections_only=args.section, dry_run=args.dry_run)

    # If failures present, exit non-zero to surface test failure
    if res.get("failures"):
        logging.error("Script completed with failures: %s", res["failures"])
        sys.exit(2)

    logging.info("Script completed successfully.")


if __name__ == "__main__":
    main()
