from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import json
import random


class YoutubeUploader:
    def __init__(self):
        # Load saved credentials
        if not os.path.exists("src/youtube/token.json"):
            raise FileNotFoundError("Google API Token file not found.")
        self.creds = Credentials.from_authorized_user_file(
            "src/youtube/token.json", ["https://www.googleapis.com/auth/youtube.upload"]
        )

    def upload_video(
        self,
        title,
        description,
        video_file_path,
    ):
        if not os.path.exists(video_file_path):
            raise FileNotFoundError(
                f"Cant upload video. Local file not found: {video_file_path}"
            )

        youtube = build("youtube", "v3", credentials=self.creds)

        request_body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": ["shorts"],
                "categoryId": "22",  # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_file_path,
            chunksize=-1,
            resumable=True,
        )

        request = youtube.videos().insert(
            part="snippet,status", body=request_body, media_body=media
        )

        response = request.execute()
        print("Video uploaded:", response["id"])


class YoutubePostHistoryManager:
    def __init__(self):
        self.fp = r"data/youtube_post_history.csv"
        if not os.path.exists(self.fp):
            with open(self.fp, "w") as f:
                f.write("video_folder_name1,video_folder_name2")

    def add_post(self, video_folder_name):
        with open(self.fp, "a") as f:
            f.write(f",{video_folder_name}")

    def post_exists(self, video_folder_name):
        with open(self.fp, "r") as f:
            content = f.read()
            return video_folder_name in content.split(",")


def extract_metadata_from_folder(video_subfolder_path):
    metadata_json_path = os.path.join(video_subfolder_path, "metadata.json")
    with open(metadata_json_path, "r") as f:
        metadata = json.load(f)
        if "title" not in metadata or "description" not in metadata:
            print(
                f"[!] Warning: this metadata.json file is missing title or description keys:\n{metadata_json_path}"
            )
            return False

    return sanitize_metadata(metadata)


def sanitize_metadata(metadata):
    def remove_chars(chars, string):
        for char in chars:
            string = string.replace(char, "")

        return string.strip()

    blacklist_chars = [
        "---",  # em dash sequence (YouTube titles usually use single dash)
        "{",
        "}",  # rarely seen in titles
        "<",
        ">",  # HTML-like symbols, never in titles
        "\\",  # backslash
        "|",  # pipe
        "@",  # used for mentions, but not title-safe
        "%",
        "^",
        "*",
        "+",
        "=",
        "`",
        "~",  # code/math/technical chars
        "—",
        "–",  # fancy em/en dashes
        "‘",
        "’",
        "“",
        "”",  # smart quotes
        "…",
        "«",
        '"',
        "»",
        "‹",
        "›",  # ellipsis, chevrons
        "•",
        "·",
        "°",  # bullets, degrees
        "  ",  # double space
        "\t",
        "\n",  # tabs and newlines
    ]

    new_data = {}
    title = metadata.get("title", "")
    description = metadata.get("description", "")
    title = remove_chars(blacklist_chars, title)
    description = remove_chars(blacklist_chars, description)
    new_data["title"] = title
    new_data["description"] = description
    return new_data


def upload_from_final_vids():
    # parse by unposted videos
    post_history_module = YoutubePostHistoryManager()
    videos_folder = r"final_vids"
    all_subfolders = os.listdir(videos_folder)
    unposted_subfolders = [
        f for f in all_subfolders if not post_history_module.post_exists(f)
    ]
    print(
        f"{len(unposted_subfolders)} of {len(all_subfolders)} videos have not been posted yet."
    )

    # select one to post
    selected_subfolder = random.choice(unposted_subfolders)
    selected_subfolder_path = os.path.join(videos_folder, selected_subfolder)
    video_path = os.path.join(selected_subfolder_path, "video.mp4")

    # extract metadata
    metadata = extract_metadata_from_folder(selected_subfolder_path)
    if metadata is False:
        print("[!] Fatal error: Cannot post due to failure to read post metadata")
        return False
    title = metadata["title"]
    description = metadata["description"]

    print(f"\nPOST METADATA HUMAN CHECK")
    print(f"Title: {title}")
    print(f"Description: {description}")
    input(f"Good to go? Press Enter to continue or Ctrl+C to cancel.")

    # upload it using the uploader
    uploader = YoutubeUploader()
    video_title = title
    video_description = description
    video_file_path = video_path  # Replace with your video file path
    uploader.upload_video(video_title, video_description, video_file_path)

    # add to post history
    post_history_module.add_post(selected_subfolder)


if __name__ == "__main__":
    upload_from_final_vids()
