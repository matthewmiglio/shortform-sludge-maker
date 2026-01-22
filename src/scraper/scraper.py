import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import os
import random


def decode_surrogates(s):
    return s.encode("utf-16", "surrogatepass").decode("utf-16")


class Post:
    def __init__(self, username, profile_img, content, thread_name, title, url):
        self.username = username
        self.profile_img = profile_img
        self.content = content
        self.thread_name = thread_name
        self.title = title
        self.url = url

    def to_dict(self):
        return {
            "username": self.username,
            "profile_img": self.profile_img,
            "content": self.content,
            "thread_name": self.thread_name,
            "title": self.title,
            "url": self.url,
        }


class RedditScraper:
    def __init__(self, stop_flag=None):
        chrome_options = Options()

        # Use same options as test_scraper.py (proven to work)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")

        # Single attempt initialization (no retry spam)
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        print("Chrome driver initialized successfully")

        self.saver = DataSaver()
        self.stop_flag = stop_flag

    def check_if_blocked(self):
        """Check if blocked by Reddit and raise exception if so."""
        if "You've been blocked by network security" in self.driver.page_source:
            raise Exception("BLOCKED: 'You've been blocked by network security'")

    def get_posts(self, thread_link, max_posts=50, scroll_pause=0.2, max_scrolls=200):
        # Convert to old.reddit.com to avoid captchas
        thread_link = thread_link.replace("www.reddit.com", "old.reddit.com")
        self.driver.get(thread_link)
        time.sleep(random.uniform(3, 7))

        # Check if blocked and pause if so
        self.check_if_blocked()

        post_links = set()
        scrolls = 0

        last_height = self.driver.execute_script("return document.body.scrollHeight")

        while len(post_links) < max_posts and scrolls < max_scrolls:
            if self.stop_flag and self.stop_flag.is_set():
                print(f"[!] Stop flag detected during scroll in {thread_link}")
                return list(post_links)

            # Scroll to bottom with random delay
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(scroll_pause + random.uniform(0.1, 0.5))

            # Look for new posts (old.reddit.com uses different selectors)
            posts = self.driver.find_elements(By.CSS_SELECTOR, "a.title")
            for post in posts:
                href = post.get_attribute("href")
                if href and "/comments/" in href:
                    if self.saver.data_exists(href):
                        # print(f"Post {href} already exists, skipping...")
                        continue
                    post_links.add(href)

            # Check if the scroll did anything
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break  # No more content
            last_height = new_height
            scrolls += 1
            print(f"Scroll {scrolls}, collected {len(post_links)} links")

        print(f"Scraped a total of {len(post_links)} post links.")
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
        print("Starting to scrape post:", post_link)
        scrape_start_time = time.time()
        print("Getting to page...")

        # Convert to old.reddit.com
        post_link = post_link.replace("www.reddit.com", "old.reddit.com")
        self.driver.get(post_link)
        time.sleep(random.uniform(4, 8))

        if self.check_for_captcha():
            print(f"[!] CAPTCHA detected for {post_link}, skipping...")
            return None

        # old.reddit.com doesn't have "Read more" buttons in the same way
        # Content is usually fully visible

        # repeatedly scrape content until we get all necessary data
        timeout = 10  # s
        username, profile_img, content, title = None, None, None, None
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
                if profile_img is None:
                    # Try to get subreddit icon for old.reddit
                    profile_img = self.driver.find_element(
                        By.CSS_SELECTOR, "img.icon"
                    )
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
            if None not in (username, profile_img, content, title):
                break

        post = Post(
            username=username,
            profile_img=profile_img.get_attribute("src") if profile_img else None,
            content=content,
            thread_name=self.url2thread_name(post_link),
            title=title,
            url=post_link,
        )
        print(f"Scraped {post_link} in {time.time() - scrape_start_time:.2f}s!")
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

        # check if already exists
        url = post.url
        if self.data_exists(url):
            # print(f"Post {url} already exists, skipping save.")
            return

        data = post.to_dict()
        # make a uuid for this file name
        file_name = (
            "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=20))
            + ".json"
        )
        file_path = os.path.join(self.data_folder_path, file_name)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Saved this post data. There are now ~{self.file_count} posts saved!")

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
                        data["profile_img"],
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
    scraper = RedditScraper(stop_flag=stop_flag)
    data_saver = DataSaver()

    try:
        if stop_flag and stop_flag.is_set():
            print(f"[!] Stop flag set before starting {thread_url}")
            scraper.driver.quit()
            return

        post_links = scraper.get_posts(thread_url, max_posts=posts_to_scrape)[
            :posts_to_scrape
        ]

        if stop_flag and stop_flag.is_set():
            print(f"[!] Stopping thread for {thread_url} after getting post links")
            scraper.driver.quit()
            return

        random.shuffle(post_links)

        for post_link in post_links:
            if stop_flag and stop_flag.is_set():
                print(f"[!] Stopping thread for {thread_url}")
                scraper.driver.quit()
                return
            if posts_scraped >= posts_to_scrape:
                break
            post = scraper.get_post_content(post_link)
            if post is not None:
                data_saver.save_post_data(post)
                posts_scraped += 1
            else:
                print(f"[!] Skipping post due to captcha or error")
                time.sleep(random.uniform(10, 20))

    except Exception as e:
        print(f"Error scraping thread {thread_url}: {e}")
    finally:
        try:
            scraper.driver.quit()
            print(f"[!] Browser closed for {thread_url}")
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
