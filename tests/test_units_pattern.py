#!/usr/bin/env python3
"""Test units pattern detection"""

import re


def test_units_pattern_detection():
    """Test that units pattern correctly detects insulin units."""
    text = "Only rapid-acting insulin at a concentration of 100 U/ml should be used"
    
    UNITS_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(u|units?)\b", re.IGNORECASE)
    
    matches = UNITS_PATTERN.findall(text)
    assert matches == [('100', 'U')], f"Expected [('100', 'U')], got {matches}"
    
    # Test finditer
    found_matches = []
    for match in UNITS_PATTERN.finditer(text):
        found_matches.append(match.group(0))
    
    assert found_matches == ['100 U'], f"Expected ['100 U'], got {found_matches}"


def test_units_pattern_variations():
    """Test units pattern with various formats."""
    UNITS_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*(u|units?)\b", re.IGNORECASE)
    
    test_cases = [
        ("take 5 units", [('5', 'units')]),
        ("inject 2.5U", [('2.5', 'U')]),
        ("10 units insulin", [('10', 'units')]),
        ("no units here", []),
    ]
    
    for text, expected in test_cases:
        matches = UNITS_PATTERN.findall(text)
        assert matches == expected, f"For '{text}', expected {expected}, got {matches}"