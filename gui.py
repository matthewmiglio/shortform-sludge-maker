import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import random
import os
import sys
import subprocess
import shutil
from io import StringIO

from src.scraper.scraper import scrape_all_threads
from video_maker import create_all_stacked_reddit_scroll_videos
from src.youtube.youtube_upload import (
    YoutubeUploader,
    YoutubePostHistoryManager,
    extract_metadata_from_folder,
)


class TextRedirector:
    def __init__(self, text_widget, tag="stdout"):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, text):
        self.text_widget.after(0, self._write, text)

    def _write(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, text, (self.tag,))
        self.text_widget.see(tk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Slop Media Machine")
        self.geometry("850x700")
        self.configure(bg="#1e1e1e")

        # Global stop flag for all operations
        self.global_stop_flag = threading.Event()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.stats = {
            "posts_scraped": 0,
            "videos_created": 0,
        }

        title_label = tk.Label(
            self,
            text="Slop Media Machine",
            font=("Helvetica", 20, "bold"),
            bg="#1e1e1e",
            fg="white",
        )
        title_label.pack(pady=15)

        main_container = tk.Frame(self, bg="#1e1e1e")
        main_container.pack(fill="both", expand=True, padx=10, pady=5)

        left_panel = tk.Frame(main_container, bg="#1e1e1e")
        left_panel.pack(side="left", fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "TNotebook",
            background="#1e1e1e",
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#2e2e2e",
            foreground="white",
            padding=[20, 10],
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#3e3e3e")],
            foreground=[("selected", "white")],
        )

        self.notebook = ttk.Notebook(left_panel)
        self.notebook.pack(fill="both", expand=True)

        self.scraper_tab = ScraperTab(self.notebook, self)
        self.video_tab = VideoTab(self.notebook, self)
        self.upload_tab = UploadTab(self.notebook, self)

        self.notebook.add(self.scraper_tab, text="Scrape Reddit")
        self.notebook.add(self.video_tab, text="Make Videos")
        self.notebook.add(self.upload_tab, text="Post Videos")

        right_panel = tk.Frame(main_container, bg="#1e1e1e")
        right_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))

        terminal_label = tk.Label(
            right_panel,
            text="Terminal Output",
            font=("Helvetica", 12, "bold"),
            bg="#1e1e1e",
            fg="white",
        )
        terminal_label.pack(pady=(0, 5))

        self.terminal = scrolledtext.ScrolledText(
            right_panel,
            wrap=tk.WORD,
            bg="#0d0d0d",
            fg="#00ff00",
            font=("Consolas", 9),
            state="disabled",
            relief="sunken",
            borderwidth=2,
        )
        self.terminal.pack(fill="both", expand=True)

        button_frame = tk.Frame(right_panel, bg="#1e1e1e")
        button_frame.pack(pady=5)

        tk.Button(
            button_frame,
            text="Clear Terminal",
            command=self.clear_terminal,
            bg="#555555",
            fg="white",
            width=15,
        ).pack(side="left", padx=2)

        tk.Button(
            button_frame,
            text="Copy Log",
            command=self.copy_log,
            bg="#555555",
            fg="white",
            width=15,
        ).pack(side="left", padx=2)

        self.stats_bar = tk.Label(
            self, text="", bg="#2e2e2e", fg="lightgray", anchor="w", padx=10, pady=5
        )
        self.stats_bar.pack(side="bottom", fill="x")

        sys.stdout = TextRedirector(self.terminal, "stdout")
        sys.stderr = TextRedirector(self.terminal, "stderr")

        self.terminal.tag_config("stdout", foreground="#00ff00")
        self.terminal.tag_config("stderr", foreground="#ff0000")

        self.log_to_terminal("Slop Media Machine initialized")
        self.log_to_terminal("Ready to start operations")

        self.refresh_stats()

    def log_to_terminal(self, message):
        print(message)

    def clear_terminal(self):
        self.terminal.configure(state="normal")
        self.terminal.delete(1.0, tk.END)
        self.terminal.configure(state="disabled")

    def copy_log(self):
        log_content = self.terminal.get(1.0, tk.END)
        self.clipboard_clear()
        self.clipboard_append(log_content)
        self.log_to_terminal("Log copied to clipboard")

    def on_close(self):
        print("\nShutting down application...")
        self.global_stop_flag.set()

        # Stop scraper if running
        if hasattr(self, 'scraper_tab'):
            self.scraper_tab.stop_flag.set()

        # Stop video generation if running
        if hasattr(self, 'video_tab'):
            self.video_tab.stop_flag.set()

        # Force exit after a short delay
        self.after(500, self._force_exit)

    def _force_exit(self):
        print("Exiting...")
        self.destroy()
        os._exit(0)

    def refresh_stats(self):
        scraped_posts_folder = r"reddit_data"
        final_videos_folder = r"final_vids"
        youtube_history_file = r"data/youtube_post_history.csv"

        scraped_posts_count = (
            len(os.listdir(scraped_posts_folder))
            if os.path.exists(scraped_posts_folder)
            else 0
        )
        final_videos_count = (
            len(os.listdir(final_videos_folder))
            if os.path.exists(final_videos_folder)
            else 0
        )
        youtube_uploads_count = 0
        if os.path.exists(youtube_history_file):
            with open(youtube_history_file, "r") as f:
                content = f.read().strip()
                if content:
                    youtube_uploads_count = len(content.split(","))

        self.stats["posts_scraped"] = scraped_posts_count
        self.stats["videos_created"] = final_videos_count
        self.stats["youtube_uploads"] = youtube_uploads_count

        self.stats_bar.config(
            text=f"Posts Scraped: {self.stats['posts_scraped']} | Videos Made: {self.stats['videos_created']} | YouTube Uploads: {self.stats['youtube_uploads']}"
        )

        self.after(10000, self.refresh_stats)


class ScraperTab(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller
        self.scrape_thread = None
        self.stop_flag = threading.Event()

        tk.Label(
            self,
            text="Scrape Reddit for storytelling content",
            bg="#1e1e1e",
            fg="gray",
            font=("Helvetica", 10),
        ).pack(pady=10)

        settings_frame = tk.Frame(self, bg="#1e1e1e")
        settings_frame.pack(pady=10)

        tk.Label(
            settings_frame, text="Posts per thread:", bg="#1e1e1e", fg="white"
        ).pack(side="left", padx=5)

        self.thread_count = tk.IntVar(value=500)
        tk.Entry(settings_frame, textvariable=self.thread_count, width=10).pack(
            side="left", padx=5
        )

        button_frame = tk.Frame(self, bg="#1e1e1e")
        button_frame.pack(pady=20)

        tk.Button(
            button_frame,
            text="Start Scraping",
            command=self.start_scraper,
            width=15,
            bg="#4CAF50",
            fg="white",
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="Stop Scraping",
            command=self.stop_scraper,
            width=15,
            bg="#f44336",
            fg="white",
        ).pack(side="left", padx=5)

        self.status_label = tk.Label(
            self, text="", bg="#1e1e1e", fg="lightgreen", wraplength=300
        )
        self.status_label.pack(pady=10, padx=20)

    def start_scraper(self):
        def run():
            self.stop_flag.clear()
            self.status_label.config(text="Scraping started...", fg="yellow")
            print("\n" + "="*50)
            print("STARTING REDDIT SCRAPER")
            print("="*50)
            try:
                threads = [
                    "https://www.reddit.com/r/tifu/",
                    "https://www.reddit.com/r/AmItheAsshole/",
                    "https://www.reddit.com/r/pettyrevenge/",
                    "https://www.reddit.com/r/ProRevenge/",
                    "https://www.reddit.com/r/raisedbynarcissists/",
                    "https://www.reddit.com/r/confession/",
                    "https://www.reddit.com/r/offmychest/",
                    "https://www.reddit.com/r/MaliciousCompliance/",
                    "https://www.reddit.com/r/karen/",
                    "https://www.reddit.com/r/TalesFromRetail/",
                    "https://www.reddit.com/r/dating/",
                    "https://www.reddit.com/r/dating_advice/",
                    "https://www.reddit.com/r/BreakUps/",
                    "https://www.reddit.com/r/TwoXChromosomes/",
                    "https://www.reddit.com/r/FemaleDatingStrategy/",
                ]
                print(f"Scraping {len(threads)} subreddits...")
                scrape_all_threads(threads, self.thread_count.get(), self.stop_flag)
                print("="*50)
                print("SCRAPING COMPLETE")
                print("="*50 + "\n")
                self.status_label.config(text="Scraping complete or stopped.", fg="lightgreen")
            except Exception as e:
                print(f"ERROR: {e}")
                self.status_label.config(text=f"Error: {e}", fg="red")

        self.scrape_thread = threading.Thread(target=run)
        self.scrape_thread.start()

    def stop_scraper(self):
        self.stop_flag.set()
        print("STOP signal sent to scraper...")
        self.status_label.config(text="Stopping scrape threads...", fg="orange")


class VideoTab(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller
        self.stop_flag = threading.Event()

        tk.Label(
            self,
            text="Generate vertical videos from scraped posts",
            bg="#1e1e1e",
            fg="gray",
            font=("Helvetica", 10),
        ).pack(pady=10)

        button_frame = tk.Frame(self, bg="#1e1e1e")
        button_frame.pack(pady=20)

        tk.Button(
            button_frame,
            text="Start Generating Videos",
            command=self.start_generation,
            width=20,
            height=2,
            bg="#2196F3",
            fg="white",
            font=("Helvetica", 11),
        ).pack(side="left", padx=5)

        tk.Button(
            button_frame,
            text="Stop",
            command=self.stop_generation,
            width=10,
            height=2,
            bg="#f44336",
            fg="white",
            font=("Helvetica", 11),
        ).pack(side="left", padx=5)

        self.status_label = tk.Label(
            self, text="", bg="#1e1e1e", fg="lightgreen", wraplength=300
        )
        self.status_label.pack(pady=10, padx=20)

    def start_generation(self):
        def run():
            self.stop_flag.clear()
            self.status_label.config(text="Video generation started...", fg="yellow")
            print("\n" + "="*50)
            print("STARTING VIDEO GENERATION")
            print("="*50)
            try:
                create_all_stacked_reddit_scroll_videos(output_dir=r"final_vids", stop_flag=self.stop_flag)
                print("="*50)
                print("VIDEO GENERATION STOPPED" if self.stop_flag.is_set() else "VIDEO GENERATION COMPLETE")
                print("="*50 + "\n")
                self.status_label.config(text="Video generation stopped." if self.stop_flag.is_set() else "All videos created!", fg="lightgreen")
            except Exception as e:
                print(f"ERROR: {e}")
                self.status_label.config(text=f"Error: {e}", fg="red")

        threading.Thread(target=run).start()

    def stop_generation(self):
        self.stop_flag.set()
        print("STOP signal sent to video generation...")
        self.status_label.config(text="Stopping video generation...", fg="orange")


class UploadTab(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e1e")
        self.controller = controller
        self.metadata = None
        self.video_path = None
        self.selected_subfolder = None

        tk.Label(
            self,
            text="Upload videos to YouTube",
            bg="#1e1e1e",
            fg="gray",
            font=("Helvetica", 10),
        ).pack(pady=10)

        tk.Button(
            self,
            text="Select Random Unposted Video",
            command=self.select_video,
            width=25,
            bg="#9C27B0",
            fg="white",
        ).pack(pady=10)

        self.metadata_frame = tk.Frame(self, bg="#2e2e2e", relief="ridge", borderwidth=2)
        self.metadata_frame.pack(pady=10, padx=20, fill="both", expand=True)

        tk.Label(
            self.metadata_frame,
            text="Video Preview",
            bg="#2e2e2e",
            fg="lightgray",
            font=("Helvetica", 10, "bold"),
        ).pack(pady=5)

        self.title_label = tk.Label(
            self.metadata_frame,
            text="No video selected",
            bg="#2e2e2e",
            fg="white",
            wraplength=300,
            justify="left",
        )
        self.title_label.pack(anchor="w", pady=5, padx=10)

        self.description_label = tk.Label(
            self.metadata_frame,
            text="",
            bg="#2e2e2e",
            fg="lightgray",
            wraplength=300,
            justify="left",
        )
        self.description_label.pack(anchor="w", pady=5, padx=10)

        self.upload_button = tk.Button(
            self,
            text="Confirm and Upload",
            command=self.upload_video,
            state="disabled",
            width=25,
            height=2,
            bg="#4CAF50",
            fg="white",
            font=("Helvetica", 12),
        )
        self.upload_button.pack(pady=15)

        tk.Button(
            self,
            text="Reauthenticate YouTube",
            command=self.reauthenticate_youtube,
            width=25,
            bg="#FF5722",
            fg="white",
        ).pack(pady=5)

        self.status_label = tk.Label(
            self, text="", bg="#1e1e1e", fg="lightgreen", wraplength=300
        )
        self.status_label.pack(pady=10, padx=20)

    def select_video(self):
        try:
            print("\nSelecting random unposted video...")
            post_history_module = YoutubePostHistoryManager()
            videos_folder = r"final_vids"

            if not os.path.exists(videos_folder):
                self.status_label.config(
                    text="Error: final_vids folder not found", fg="red"
                )
                print("ERROR: final_vids folder not found")
                return

            all_subfolders = os.listdir(videos_folder)

            # filter to unposted videos by checking reddit_url in metadata
            unposted_subfolders = []
            for subfolder in all_subfolders:
                subfolder_path = os.path.join(videos_folder, subfolder)
                metadata = extract_metadata_from_folder(subfolder_path)
                if metadata is False:
                    continue
                reddit_url = metadata.get("reddit_url", "")
                if reddit_url and not post_history_module.post_exists(reddit_url):
                    unposted_subfolders.append((subfolder, metadata))

            if not unposted_subfolders:
                self.status_label.config(text="No unposted videos found", fg="orange")
                print("No unposted videos found")
                return

            self.status_label.config(
                text=f"{len(unposted_subfolders)} of {len(all_subfolders)} videos unposted",
                fg="lightblue",
            )
            print(f"Found {len(unposted_subfolders)} unposted videos out of {len(all_subfolders)} total")

            self.selected_subfolder, self.metadata = random.choice(unposted_subfolders)
            selected_subfolder_path = os.path.join(videos_folder, self.selected_subfolder)
            self.video_path = os.path.join(selected_subfolder_path, "video.mp4")

            print(f"Selected: {self.selected_subfolder}")
            print(f"Title: {self.metadata['title']}")
            print(f"Description: {self.metadata['description'][:100]}...")

            self.title_label.config(text=f"[{self.selected_subfolder}]\n\nTitle:\n{self.metadata['title']}")
            self.description_label.config(
                text=f"\nDescription:\n{self.metadata['description']}"
            )
            self.upload_button.config(state="normal")
            self.status_label.config(
                text="Video selected. Review and confirm upload.", fg="lightgreen"
            )

        except Exception as e:
            print(f"ERROR: {e}")
            self.status_label.config(text=f"Error: {e}", fg="red")

    def upload_video(self):
        def run():
            try:
                self.status_label.config(text="Uploading to YouTube...", fg="yellow")
                self.upload_button.config(state="disabled")

                print("\n" + "="*50)
                print("UPLOADING VIDEO TO YOUTUBE")
                print("="*50)
                print(f"Video: {self.selected_subfolder}")

                uploader = YoutubeUploader()
                uploader.upload_video(
                    self.metadata["title"],
                    self.metadata["description"],
                    self.video_path,
                )

                reddit_url = self.metadata.get("reddit_url", "")
                if reddit_url:
                    post_history_module = YoutubePostHistoryManager()
                    post_history_module.add_post(reddit_url)

                # Delete the video folder after successful upload
                selected_subfolder_path = os.path.join("final_vids", self.selected_subfolder)
                shutil.rmtree(selected_subfolder_path)
                print(f"Deleted uploaded video folder: {self.selected_subfolder}")

                print("="*50)
                print("UPLOAD COMPLETE")
                print("="*50 + "\n")

                self.status_label.config(
                    text="Video uploaded successfully!", fg="lightgreen"
                )
                self.title_label.config(text="No video selected")
                self.description_label.config(text="")
                self.metadata = None
                self.video_path = None
                self.selected_subfolder = None

            except Exception as e:
                print(f"ERROR: Upload failed - {e}")
                self.status_label.config(text=f"Upload failed: {e}", fg="red")
                self.upload_button.config(state="normal")

        threading.Thread(target=run).start()

    def reauthenticate_youtube(self):
        def run():
            try:
                self.status_label.config(text="Starting YouTube authentication...", fg="yellow")
                print("\n" + "="*50)
                print("STARTING YOUTUBE REAUTHENTICATION")
                print("="*50)
                print("A browser window will open for authentication...")
                print("Please complete the authentication in your browser.")

                auth_script_path = os.path.join("src", "youtube", "youtube_auth.py")

                result = subprocess.run(
                    [sys.executable, auth_script_path],
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    print(result.stdout)
                    print("="*50)
                    print("AUTHENTICATION COMPLETE")
                    print("="*50 + "\n")
                    self.status_label.config(
                        text="YouTube reauthentication successful!", fg="lightgreen"
                    )
                else:
                    print(f"STDOUT: {result.stdout}")
                    print(f"STDERR: {result.stderr}")
                    print("="*50)
                    print("AUTHENTICATION FAILED")
                    print("="*50 + "\n")
                    self.status_label.config(
                        text=f"Authentication failed: {result.stderr[:100]}", fg="red"
                    )

            except Exception as e:
                print(f"ERROR: Authentication failed - {e}")
                self.status_label.config(text=f"Authentication error: {e}", fg="red")

        threading.Thread(target=run).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
