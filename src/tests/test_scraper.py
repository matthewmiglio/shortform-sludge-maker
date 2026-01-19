import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import threading

# Import from scraper
from src.scraper.scraper import Post

def test_scraper():
    print("=" * 60)
    print("REDDIT SCRAPER TEST")
    print("=" * 60)

    scraper_driver = None

    try:
        # Test 1: Initialize Chrome (single attempt, no retries)
        print("\n[1/3] Testing Chrome initialization...")

        # Try minimal options first
        configs_to_try = [
            ("Minimal (no-sandbox + disable-dev-shm)", [
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]),
            ("With maximized", [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--start-maximized"
            ]),
            ("Headless mode", [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--headless=new"
            ]),
        ]

        for config_name, args in configs_to_try:
            try:
                print(f"    Trying {config_name}...")
                chrome_options = Options()
                for arg in args:
                    chrome_options.add_argument(arg)

                scraper_driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()),
                    options=chrome_options
                )
                print(f"    [OK] Chrome initialized successfully with {config_name}")
                break
            except Exception as e:
                print(f"    [FAIL] {config_name} failed")
                if config_name == configs_to_try[-1][0]:  # Last attempt
                    print(f"    Error: {e}")
                    return False
                continue

        # Test 2: Visit a Reddit thread
        print("\n[2/3] Testing Reddit page navigation...")
        test_url = "https://old.reddit.com/r/AmItheAsshole/"
        try:
            scraper_driver.get(test_url)
            time.sleep(5)
            print(f"    [OK] Successfully navigated to {test_url}")

            # Check for actual captcha blocking (not just the word in forms)
            page_source = scraper_driver.page_source
            # Look for actual captcha challenge page elements
            if ("challenge" in page_source.lower() and "captcha" in page_source.lower()) or \
               "you have been blocked" in page_source.lower() or \
               "access denied" in page_source.lower():
                print("    [WARN] Captcha/block detected on thread page")
                print("    This means Reddit is blocking automated access")
                return False
            else:
                print("    [OK] No captcha detected on thread page")
        except Exception as e:
            print(f"    [FAIL] Failed to navigate to Reddit: {e}")
            return False

        # Test 3: Try to find and scrape a single post
        print("\n[3/3] Testing post scraping...")
        try:
            # Find post links (old.reddit.com uses different CSS)
            print("    Looking for post links...")
            posts = scraper_driver.find_elements(By.CSS_SELECTOR, "a.title")
            post_links = []
            for post in posts:
                href = post.get_attribute("href")
                if href and "/comments/" in href:
                    post_links.append(href)
                    if len(post_links) >= 3:
                        break

            if not post_links:
                print("    [FAIL] No post links found")
                return False

            print(f"    [OK] Found {len(post_links)} post links")

            # Try to scrape the first post
            test_post_url = post_links[0]
            print(f"    Testing post: {test_post_url}")

            scraper_driver.get(test_post_url)
            time.sleep(5)

            # Check for actual captcha blocking on post page
            page_source = scraper_driver.page_source
            if ("challenge" in page_source.lower() and "captcha" in page_source.lower()) or \
               "you have been blocked" in page_source.lower() or \
               "access denied" in page_source.lower():
                print("    [FAIL] Captcha/block detected on post page")
                return False

            # Try to get post content (old.reddit.com selectors)
            username = None
            content = None
            title = None

            try:
                username = scraper_driver.find_element(By.CSS_SELECTOR, "a.author").text
            except:
                pass

            try:
                content = scraper_driver.find_element(By.CSS_SELECTOR, "div.usertext-body").text
            except:
                pass

            try:
                title = scraper_driver.find_element(By.CSS_SELECTOR, "a.title").text
            except:
                pass

            if not username or not content or not title:
                print("    [FAIL] Could not extract post data")
                print(f"        Username: {username}")
                print(f"        Content length: {len(content) if content else 0}")
                print(f"        Title: {title}")
                return False

            print("    [OK] Successfully scraped post:")
            print(f"        Username: {username}")
            print(f"        Title: {title[:60]}...")
            print(f"        Content length: {len(content)} chars")

            return True

        except Exception as e:
            print(f"    [FAIL] Failed to scrape post: {e}")
            import traceback
            traceback.print_exc()
            return False

    finally:
        # ALWAYS cleanup - even if tests fail
        print("\n[Cleanup] Closing browser...")
        if scraper_driver:
            try:
                scraper_driver.quit()
                print("    [OK] Browser closed successfully")
            except Exception as e:
                print(f"    [WARN] Warning during cleanup: {e}")

if __name__ == "__main__":
    print("\nStarting scraper test...\n")

    success = test_scraper()

    print("\n" + "=" * 60)
    if success:
        print("[PASS] ALL TESTS PASSED")
        print("=" * 60)
        sys.exit(0)
    else:
        print("[FAIL] TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
