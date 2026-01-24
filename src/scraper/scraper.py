import threading
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import json
import os
import random

from src.metadata.scoring import score_post, MIN_ENGAGEMENT, MIN_REPOST_QUALITY


def decode_surrogates(s):
    return s.encode("utf-16", "surrogatepass").decode("utf-16")


class Post:
    def __init__(self, username, content, thread_name, title, url):
        self.username = username
        self.content = content
        self.thread_name = thread_name
        self.title = title
        self.url = url

    def to_dict(self):
        return {
            "username": self.username,
            "content": self.content,
            "thread_name": self.thread_name,
            "title": self.title,
            "url": self.url,
        }


class RedditScraper:
    def __init__(self, stop_flag=None):
        self._browser_pid = None
        chrome_options = uc.ChromeOptions()

        # Anti-detection options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        # Additional anti-detection
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--lang=en-US")
        chrome_options.add_argument("--window-size=1920,1080")

        # Use undetected-chromedriver with version matching
        # use_subprocess=True helps avoid detection
        self.driver = uc.Chrome(options=chrome_options, version_main=143, use_subprocess=True)

        # Store the browser PID for cleanup
        self._browser_pid = None
        self._service_pid = None
        try:
            self._browser_pid = self.driver.browser_pid
            print(f"Browser PID: {self._browser_pid}")
        except Exception as e:
            print(f"[!] Could not get browser PID: {e}")
        try:
            # The service (chromedriver) PID is often more reliable
            if hasattr(self.driver, 'service') and self.driver.service:
                self._service_pid = self.driver.service.process.pid
                print(f"Service PID: {self._service_pid}")
        except Exception as e:
            print(f"[!] Could not get service PID: {e}")
        print("Chrome driver initialized successfully")

        # Execute CDP commands to further mask automation
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = {runtime: {}};
            """
        })

        # Warmup chain: Google → reddit.com → then subreddit
        print("[0/4] Warming up browser...")
        self.driver.get("https://www.google.com")
        time.sleep(random.uniform(2, 4))

        print("[0/4] Visiting reddit.com...")
        self.driver.get("https://www.reddit.com")
        time.sleep(random.uniform(3, 5))

        self.saver = DataSaver()
        self.stop_flag = stop_flag

    def close(self):
        """Clean up the browser."""
        import subprocess
        import sys

        # Get the user-data-dir before quitting - we'll use it to find orphaned processes
        user_data_dir = None
        try:
            for arg in self.driver.options.arguments:
                if "--user-data-dir=" in arg:
                    user_data_dir = arg.split("=", 1)[1]
                    break
        except:
            pass

        # Try to quit gracefully first
        try:
            self.driver.quit()
            print("[!] driver.quit() completed")
        except Exception as e:
            print(f"[!] driver.quit() failed: {e}")

        # Force kill by user-data-dir (most reliable for undetected_chromedriver)
        if user_data_dir and sys.platform == "win32":
            print(f"[!] Searching for Chrome with user-data-dir: {user_data_dir}")
            try:
                # Use PowerShell to find Chrome processes by command line
                ps_cmd = f'''Get-CimInstance Win32_Process -Filter "name='chrome.exe'" | Where-Object {{ $_.CommandLine -like '*{user_data_dir.replace("'", "''")}*' }} | Select-Object -ExpandProperty ProcessId'''
                result = subprocess.run(
                    ["powershell", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=15
                )
                pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip().isdigit()]
                for pid in pids:
                    print(f"[!] Killing Chrome PID {pid} (matched user-data-dir)")
                    subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                                 capture_output=True, timeout=10)
                if pids:
                    print(f"[!] Killed {len(pids)} Chrome process(es)")
            except Exception as e:
                print(f"[!] PowerShell search failed: {e}")

        # Fallback: kill by stored PIDs
        for pid, name in [(self._service_pid, "service"), (self._browser_pid, "browser")]:
            if pid:
                try:
                    if sys.platform == "win32":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                      capture_output=True, timeout=10)
                except:
                    pass

        print("[!] Browser closed")

    def check_if_blocked(self):
        """Check if blocked by Reddit and raise exception if so."""
        if "You've been blocked by network security" in self.driver.page_source:
            raise Exception("BLOCKED: 'You've been blocked by network security'")

    def get_posts(self, thread_link, max_posts=50, scroll_pause=0.2, max_scrolls=200):
        # Convert to old.reddit.com to avoid captchas
        thread_link = thread_link.replace("www.reddit.com", "old.reddit.com")
        print(f"[1/4] Visiting subreddit: {thread_link}")
        self.driver.get(thread_link)
        time.sleep(random.uniform(3, 7))

        # Check if blocked and pause if so
        self.check_if_blocked()
        print(f"[1/4] Successfully loaded subreddit page")

        post_links = set()
        page_num = 1

        while len(post_links) < max_posts:
            if self.stop_flag and self.stop_flag.is_set():
                print(f"[!] Stop flag detected during scrape in {thread_link}")
                return list(post_links)

            # Scroll down the page to load any lazy content
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_scroll_attempts = 5

            while scroll_attempts < max_scroll_attempts:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(scroll_pause + random.uniform(1.5, 3.0))
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_attempts += 1

            # Collect post links from current page
            posts_before = len(post_links)
            posts = self.driver.find_elements(By.CSS_SELECTOR, "a.title")
            for post in posts:
                href = post.get_attribute("href")
                if href and "/comments/" in href:
                    if self.saver.data_exists(href):
                        continue
                    post_links.add(href)

            print(f"[2/4] Page {page_num}: found {len(post_links)} post links (+{len(post_links) - posts_before} new)")

            # Check if we have enough posts
            if len(post_links) >= max_posts:
                break

            # Try to find and click the "next" button for pagination
            # Multiple selectors to handle different page layouts
            next_url = None
            next_selectors = [
                ".next-button a",
                "span.next-button a",
                ".nav-buttons .next-button a",
                "a[rel*='next']",
            ]
            for selector in next_selectors:
                try:
                    next_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    next_url = next_button.get_attribute("href")
                    if next_url:
                        break
                except:
                    continue

            if next_url:
                print(f"Going to next page...")
                self.driver.get(next_url)
                time.sleep(random.uniform(3, 6))
                self.check_if_blocked()
                page_num += 1
            else:
                print("No next button found, done collecting links")
                break

        print(f"[2/4] Done collecting links: {len(post_links)} posts from {page_num} page(s)")
        return list(post_links)

    def url2thread_name(self, url):
        # https://www.reddit.com/r/AmItheAsshole/comments/1lu69qb/aita_for_pulling_my_daughter_from_soccer_camp_and/
        # or https://old.reddit.com/r/AmItheAsshole/comments/...
        # extract the AmItheAsshole part
        try:
            # Handle both www.reddit.com and old.reddit.com
            if "reddit.com/r/" in url:
                thread_name = url.split("reddit.com/r/")[1].split("/")[0]
                return thread_name
        except:
            pass

        return None

    def check_for_captcha(self):
        page_source = self.driver.page_source.lower()
        # Look for actual captcha challenge, not just the word in forms
        if ("challenge" in page_source and "captcha" in page_source) or \
           "you have been blocked" in page_source or \
           "access denied" in page_source:
            print("[!] CAPTCHA or block detected!")
            return True
        return False

    def get_post_content(self, post_link):
        print(f"[3/4] Scraping post: {post_link}")
        scrape_start_time = time.time()

        # Convert to old.reddit.com
        post_link = post_link.replace("www.reddit.com", "old.reddit.com")
        self.driver.get(post_link)
        time.sleep(random.uniform(8, 15))

        if self.check_for_captcha():
            print(f"[!] CAPTCHA detected for {post_link}, skipping...")
            return None

        # old.reddit.com doesn't have "Read more" buttons in the same way
        # Content is usually fully visible

        # repeatedly scrape content until we get all necessary data
        timeout = 10  # s
        username, content, title = None, None, None
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if username is None:
                    # old.reddit uses "a.author" instead of "a.author-name"
                    username = self.driver.find_element(
                        By.CSS_SELECTOR, "a.author"
                    ).text
            except:
                pass

            try:
                if content is None:
                    # old.reddit post content is in div.expando > form > div.md
                    # This avoids grabbing sidebar content
                    content = self.driver.find_element(By.CSS_SELECTOR, "div.expando div.md").text
            except:
                pass

            try:
                if title is None:
                    # old.reddit uses "a.title" for post titles
                    title = self.driver.find_element(
                        By.CSS_SELECTOR, "a.title"
                    ).text
            except:
                pass

            # if all data exists break
            if None not in (username, content, title):
                break

        post = Post(
            username=username,
            content=content,
            thread_name=self.url2thread_name(post_link),
            title=title,
            url=post_link,
        )
        print(f"[3/4] Scraped post in {time.time() - scrape_start_time:.2f}s - title: {title[:50] if title else 'None'}...")
        return post


class DataSaver:
    def __init__(self):
        self.data_folder_path = "reddit_data"
        if not os.path.exists(self.data_folder_path):
            os.makedirs(self.data_folder_path)
        self.file_count = None

    def data_exists(self, post_url):
        files = os.listdir(self.data_folder_path)
        self.file_count = len(files)
        for f in files:
            if ".json" in f:
                with open(os.path.join(self.data_folder_path, f), "r") as file:
                    data = json.load(file)
                    if data.get("url") == post_url:
                        return True
        return False

    def save_post_data(self, post: Post):
        # clean the post content before it gets written
        post.content = decode_surrogates(post.content)
        post.title = decode_surrogates(post.title)

        # skip posts with empty content
        if not post.content.strip():
            return

        # check if already exists
        url = post.url
        if self.data_exists(url):
            return

        # score the post before saving
        print(f"[4/4] Scoring post...")
        scores = score_post(post.title, post.content)
        if scores:
            eng = scores["engagement"]
            rq = scores["repost_quality"]
            print(f"[4/4] Scores: engagement={eng}, sentiment={scores['sentiment']}, repost_quality={rq}")
            if eng < MIN_ENGAGEMENT or rq < MIN_REPOST_QUALITY:
                print(f"[4/4] Skipping post (below threshold: engagement>={MIN_ENGAGEMENT}, repost_quality>={MIN_REPOST_QUALITY})")
                return
        else:
            # if scoring fails, save anyway rather than lose the post
            print("[4/4] Scoring unavailable, saving post without filtering.")

        data = post.to_dict()
        if scores:
            data["scores"] = scores
        # make a uuid for this file name
        file_name = (
            "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=20))
            + ".json"
        )
        file_path = os.path.join(self.data_folder_path, file_name)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"[4/4] Saved! There are now ~{self.file_count} posts saved.")

    def get_all_posts(self):
        posts = []
        file_names = os.listdir(self.data_folder_path)
        for file_name in file_names:
            if file_name.endswith(".json"):
                file_path = os.path.join(self.data_folder_path, file_name)
                with open(file_path, "r") as f:
                    data = json.load(f)
                    post = Post(
                        data["username"],
                        data["content"],
                        data["thread_name"],
                        data["title"],
                        data["url"],
                    )
                    posts.append(post)
        print(f"Loaded {len(posts)} posts from {self.data_folder_path}/")
        return posts


def scrape_thread(thread_url, posts_to_scrape: int, stop_flag):
    posts_scraped = 0
    scraper = None
    data_saver = DataSaver()

    try:
        scraper = RedditScraper(stop_flag=stop_flag)
        if stop_flag and stop_flag.is_set():
            print(f"[!] Stop flag set before starting {thread_url}")
            scraper.close()
            return

        post_links = scraper.get_posts(thread_url, max_posts=posts_to_scrape)[
            :posts_to_scrape
        ]

        if stop_flag and stop_flag.is_set():
            print(f"[!] Stopping thread for {thread_url} after getting post links")
            scraper.close()
            return

        random.shuffle(post_links)

        for post_link in post_links:
            if stop_flag and stop_flag.is_set():
                print(f"[!] Stopping thread for {thread_url}")
                scraper.close()
                return
            if posts_scraped >= posts_to_scrape:
                break
            post = scraper.get_post_content(post_link)
            if post is not None:
                data_saver.save_post_data(post)
                posts_scraped += 1
                time.sleep(random.uniform(10, 25))
            else:
                print(f"[!] Skipping post due to captcha or error")
                time.sleep(random.uniform(10, 20))

    except Exception as e:
        print(f"Error scraping thread {thread_url}: {e}")
    finally:
        if scraper is not None:
            try:
                scraper.close()
            except:
                pass


def scrape_all_threads(threads_to_scrape, posts_to_scrape: int, stop_flag):
    max_concurrent_threads = 1
    active_threads = []
    remaining_threads = list(threads_to_scrape)
    random.shuffle(remaining_threads)

    print(f"Starting scraper with max {max_concurrent_threads} concurrent threads")
    print(f"Total subreddits to scrape: {len(remaining_threads)}")

    while remaining_threads or active_threads:
        if stop_flag and stop_flag.is_set():
            print("Stop flag detected, waiting for active threads to finish...")
            break

        active_threads = [t for t in active_threads if t.is_alive()]

        while len(active_threads) < max_concurrent_threads and remaining_threads:
            thread_url = remaining_threads.pop(0)
            try:
                print(f"\nStarting scraper thread for: {thread_url}")
                print(f"Active threads: {len(active_threads) + 1}/{max_concurrent_threads}")
                print(f"Remaining subreddits: {len(remaining_threads)}")

                t = threading.Thread(
                    target=scrape_thread, args=(thread_url, posts_to_scrape, stop_flag)
                )
                t.start()
                active_threads.append(t)

                # Wait a bit before starting the next thread to avoid Chrome launch conflicts
                time.sleep(random.uniform(3, 6))
            except Exception as e:
                print(f"[!] Failed to start thread for {thread_url}: {e}")

        time.sleep(2)

    for t in active_threads:
        t.join()

    print("\nAll scraping threads completed!")
    return active_threads


if __name__ == "__main__":
    threads_to_scrape = [
        "https://www.reddit.com/r/tifu/",
        "https://www.reddit.com/r/AmItheAsshole/",
        "https://www.reddit.com/r/pettyrevenge/",
        "https://www.reddit.com/r/ProRevenge/",
        "https://www.reddit.com/r/raisedbynarcissists/",
        "https://www.reddit.com/r/confession/",
        "https://www.reddit.com/r/offmychest/",
        "https://www.reddit.com/r/offmychest/",
        "https://www.reddit.com/r/MaliciousCompliance/",
        "https://www.reddit.com/r/karen/",
        "https://www.reddit.com/r/TalesFromRetail/",
    ]
    scrape_all_threads(threads_to_scrape, 50, None)
