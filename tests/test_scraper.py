#!/usr/bin/env python3
"""
Test script for the Reddit scraper.
Run from project root: poetry run python tests/test_scraper.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper.scraper import scrape_all_threads


def test_scraper():
    threads_to_scrape = [
        "https://www.reddit.com/r/tifu/",
        "https://www.reddit.com/r/AmItheAsshole/",
    ]

    print("Testing scraper with 2 subreddits, 10 posts each...")
    print("=" * 50)

    scrape_all_threads(threads_to_scrape, 10, None)

    print("=" * 50)
    print("Scraper test complete.")


if __name__ == "__main__":
    test_scraper()
