#!/usr/bin/env python3
"""
ADA Standards PDF Download Helper

Interactive CLI that guides users through downloading 17 ADA Standards PDFs
from diabetesjournals.org. Prints direct links and waits for user confirmation.

Usage:
    python scripts/download_ada_helper.py          # Interactive download guide
    python scripts/download_ada_helper.py --list-only  # Just show URLs
"""

import argparse
import os
from pathlib import Path
from typing import Dict

# ADA Standards of Care 2026 - Section URLs and expected filenames
# Volume 49, Supplement 1 (January 2026)
ADA_SECTIONS = {
    "00_intro": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S1/160916/Introduction-and-Methodology",
        "filename": "section_00_introduction_and_methodology.pdf",
        "title": "Introduction and Methodology"
    },
    "00_summary": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S1/160915/Summary-of-Revisions",
        "filename": "section_00_summary_of_revisions.pdf",
        "title": "Summary of Revisions"
    },
    "01_improving_care": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S5/160919/Improving-Care-and-Promoting-Health-in",
        "filename": "section_01_improving_care.pdf",
        "title": "Improving Care and Promoting Health in Populations"
    },
    "02_diagnosis": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S17/160931/Diagnosis-and-Classification-of-Diabetes",
        "filename": "section_02_diagnosis.pdf",
        "title": "Diagnosis and Classification of Diabetes"
    },
    "03_prevention": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S18/160918/Prevention-or-Delay-of-Diabetes-and",
        "filename": "section_03_prevention.pdf",
        "title": "Prevention or Delay of Diabetes and Associated Comorbidities"
    },
    "04_evaluation": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S32/160932/Comprehensive-Medical-Evaluation-and",
        "filename": "section_04_evaluation.pdf",
        "title": "Comprehensive Medical Evaluation and Assessment of Comorbidities"
    },
    "05_behaviors": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S36/160936/Facilitating-Positive-Health-Behaviors-and",
        "filename": "section_05_behaviors.pdf",
        "title": "Facilitating Positive Health Behaviors and Well-being"
    },
    "06_glycemic_goals": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S26/160926/Glycemic-Goals-Hypoglycemia-and",
        "filename": "section_06_glycemic_goals.pdf",
        "title": "Glycemic Goals, Hypoglycemia, and Hyperglycemic Crises"
    },
    "07_technology": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S21/160921/Diabetes-Technology",
        "filename": "section_07_technology.pdf",
        "title": "Diabetes Technology"
    },
    "08_obesity": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S20/160920/Obesity-and-Weight-Management",
        "filename": "section_08_obesity.pdf",
        "title": "Obesity and Weight Management"
    },
    "09_pharmacologic": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S33/160933/Pharmacologic-Approaches-to-Glycemic",
        "filename": "section_09_pharmacologic.pdf",
        "title": "Pharmacologic Approaches to Glycemic Treatment"
    },
    "10_cardiovascular": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S34/160934/Cardiovascular-Disease-and-Risk-Management",
        "filename": "section_10_cardiovascular.pdf",
        "title": "Cardiovascular Disease and Risk Management"
    },
    "11_kidney": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S24/160924/Chronic-Kidney-Disease-and-Risk-Management",
        "filename": "section_11_kidney.pdf",
        "title": "Chronic Kidney Disease and Risk Management"
    },
    "12_retinopathy": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S25/160925/Retinopathy-Neuropathy-and-Foot-Care",
        "filename": "section_12_retinopathy.pdf",
        "title": "Retinopathy, Neuropathy, and Foot Care"
    },
    "13_older_adults": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S35/160935/Older-Adults",
        "filename": "section_13_older_adults.pdf",
        "title": "Older Adults"
    },
    "14_children": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S30/160930/Children-and-Adolescents",
        "filename": "section_14_children.pdf",
        "title": "Children and Adolescents"
    },
    "15_pregnancy": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S29/160929/Management-of-Diabetes-in-Pregnancy",
        "filename": "section_15_pregnancy.pdf",
        "title": "Management of Diabetes in Pregnancy"
    },
    "16_hospital": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S28/160928/Diabetes-Care-in-the-Hospital",
        "filename": "section_16_hospital.pdf",
        "title": "Diabetes Care in the Hospital"
    },
    "17_advocacy": {
        "url": "https://diabetesjournals.org/care/article/49/Supplement_1/S13/160913/Diabetes-Advocacy",
        "filename": "section_17_advocacy.pdf",
        "title": "Diabetes Advocacy"
    }
}

def main():
    parser = argparse.ArgumentParser(description="ADA Standards PDF Download Helper")
    parser.add_argument("--list-only", action="store_true",
                       help="Just list URLs without interactive prompts")
    args = parser.parse_args()

    # Setup paths
    project_root = Path(__file__).parent.parent
    pdf_dir = project_root / "data" / "knowledge" / "ada_standards_pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print("🩺 ADA Standards of Care 2026 - PDF Download Helper")
    print("=" * 60)
    print()
    print("This tool helps you download the 17 ADA Standards sections as PDFs.")
    print("Each PDF contains detailed clinical recommendations beyond the abstracts.")
    print()
    print(f"Save PDFs to: {pdf_dir}")
    print("Expected filename format: section_XX_title.pdf")
    print()
    print("⚠️  Legal Note: These PDFs are for personal educational use only.")
    print("   Do not redistribute. ADA copyright applies.")
    print()

    if args.list_only:
        print("📋 Direct Links to ADA Standards Sections:")
        print("-" * 50)
        for section_key, info in ADA_SECTIONS.items():
            section_num = section_key.split('_')[0]
            print(f"Section {section_num}: {info['title']}")
            print(f"  URL: {info['url']}")
            print(f"  Save as: {info['filename']}")
            print()
        return

    # Interactive mode
    downloaded_count = 0
    total_sections = len(ADA_SECTIONS)

    for section_key, info in ADA_SECTIONS.items():
        section_num = section_key.split('_')[0]
        expected_path = pdf_dir / info['filename']

        print(f"📥 Section {section_num}: {info['title']}")
        print(f"   URL: {info['url']}")
        print(f"   Save as: {info['filename']}")
        print(f"   Location: {expected_path}")
        print()

        # Check if already downloaded
        if expected_path.exists():
            print(f"✅ Already downloaded: {expected_path.name}")
        else:
            print("⬇️  Please download the PDF from the URL above")
            print("   Right-click 'Download PDF' or 'Full Text PDF' link")

        # Wait for user confirmation
        while True:
            response = input("Press Enter when downloaded (or 'skip' to continue): ").strip().lower()
            if response == 'skip':
                break
            elif response == '':
                if expected_path.exists():
                    print("✅ File verified!")
                    downloaded_count += 1
                    break
                else:
                    print("❌ File not found. Please check the filename and location.")
                    print(f"   Expected: {expected_path}")
            else:
                print("Please press Enter or type 'skip'")

        print(f"Progress: {downloaded_count}/{total_sections} sections downloaded")
        print("-" * 50)
        print()

    print("🎉 Download complete!")
    print(f"Downloaded: {downloaded_count}/{total_sections} sections")
    print()
    print("Next steps:")
    print("1. Run: python scripts/ingest_ada_standards.py")
    print("   (This will detect PDFs and ingest them automatically)")
    print()
    print("Or manually trigger PDF ingestion:")
    print("   python scripts/ingest_ada_standards.py --pdf-only")

if __name__ == "__main__":
    main()