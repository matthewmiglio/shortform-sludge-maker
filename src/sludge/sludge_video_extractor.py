import os
import random
from moviepy.video.io.VideoFileClip import VideoFileClip
import cv2


def get_video_duration(video_path):
    clip = VideoFileClip(video_path)
    duration = clip.duration
    clip.close()
    return duration


def get_subclip(input_video_path, output_video_path, start_time, end_time):
    clip = VideoFileClip(input_video_path).subclip(start_time, end_time)
    clip.write_videofile(output_video_path, codec="libx264", logger=None)
    clip.close()
    return output_video_path


def get_vid_dims(video_path):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return width, height


def stretch_video_dims(video_path, new_x, new_y, in_place=False):
    out_video_path = video_path.replace(".mp4", f"_stretched_{new_x}_{new_y}.mp4")
    cap = cv2.VideoCapture(video_path)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (new_x, new_y))
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, (new_x, new_y), interpolation=cv2.INTER_LINEAR)
        out.write(frame)

    cap.release()
    out.release()

    if in_place:
        os.remove(video_path)
        os.rename(out_video_path, video_path)
        return video_path

    return out_video_path


class Extractor:
    def __init__(self):
        self.videos_dir = r"sludge_videos"

    def get_random_sludge_video(self, target_duration, output_path, expected_dims):
        # grab a random base sludge video
        video_extensions = (".mp4", ".avi", ".mkv", ".mov", ".webm")
        all_videos = [f for f in os.listdir(self.videos_dir) if f.lower().endswith(video_extensions)]
        random_video = random.choice(all_videos)
        base_sludge_video_path = os.path.join(self.videos_dir, random_video)

        # calculate a time region for a subclip of this video
        # that matches target duration
        # but is random
        duration = int(get_video_duration(base_sludge_video_path))
        if duration < target_duration:
            print(f"Video {random_video} is too short ({duration}s), skipping.")
            return False
        possible_start_times = range(10, duration - target_duration - 10)
        start_time = random.choice(possible_start_times)
        end_time = start_time + target_duration

        get_subclip(base_sludge_video_path, output_path, start_time, end_time)

        stretch_video_dims(
            output_path, expected_dims[0], expected_dims[1], in_place=True
        )


if __name__ == "__main__":
    pass
