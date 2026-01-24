import cv2
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip


def stack_videos_vertically(top_video_path, bottom_video_path, out_video_path):
    cap1 = cv2.VideoCapture(top_video_path)
    cap2 = cv2.VideoCapture(bottom_video_path)

    # Ensure both videos are open
    if not cap1.isOpened():
        raise ValueError(
            f"top_video_path: {top_video_path} is invalid or cannot be opened."
        )
    if not cap2.isOpened():
        raise ValueError(
            f"bottom_video_path: {bottom_video_path} is invalid or cannot be opened."
        )

    # Get properties (assume same fps)
    fps = cap1.get(cv2.CAP_PROP_FPS)
    width1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    height1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

    width2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
    height2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Resize to same width (if needed)
    common_width = min(width1, width2)

    height1_resized = int(height1 * common_width / width1)
    height2_resized = int(height2 * common_width / width2)
    out_height = height1_resized + height2_resized

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (common_width, out_height))

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            break

        frame1_resized = cv2.resize(frame1, (common_width, height1_resized))
        frame2_resized = cv2.resize(frame2, (common_width, height2_resized))

        stacked = cv2.vconcat([frame1_resized, frame2_resized])
        out.write(stacked)

    cap1.release()
    cap2.release()
    out.release()


def add_audio_to_video(video_path, audio_path, out_video_path):
    # Load the video and audio
    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    try:
        # Match the audio duration to the video duration (trim if needed)
        if audio.duration > video.duration:
            audio = audio.subclip(0, video.duration)

        # Set the audio to the video
        final_video = video.set_audio(audio)

        # Write the final video
        final_video.write_videofile(out_video_path, codec="libx264", audio_codec="aac", logger=None)
    finally:
        video.close()
        audio.close()

    return out_video_path


def get_video_duration(video_path):
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    return duration


def get_video_dims(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    return width, height


def add_fade_background(main_video, fade_video, output_path):
    """
    Single-pass ffmpeg: scales fade_video to full dims, blurs it,
    then overlays the main_video (with padding) centered on top.
    """
    import subprocess

    width, height = get_video_dims(main_video)
    pad = 50
    fg_width = width - (pad * 2)
    fg_height = int(fg_width * (height / width))
    blur_sigma = 35  # approximates 71x71 Gaussian kernel
    overlay_x = (width - fg_width) // 2
    overlay_y = (height - fg_height) // 2

    filter_complex = (
        f"[1:v]scale={width}:{height},gblur=sigma={blur_sigma}[bg];"
        f"[0:v]scale={fg_width}:{fg_height}[fg];"
        f"[bg][fg]overlay={overlay_x}:{overlay_y}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", main_video,
        "-i", fade_video,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-an", output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[!] ffmpeg error in add_fade_background: {result.stderr[-300:]}")
        return False


def scroll_image(image_path, out_video_path, scroll_duration, height):
    # Load the image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("Image not found or unable to read.")

    # Get image dimensions
    img_height, img_width, _ = image.shape

    # Calculate the number of frames needed for the scroll
    fps = 30  # Frames per second
    total_frames = int(scroll_duration * fps)

    # Create a VideoWriter object
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(out_video_path, fourcc, fps, (img_width, height))

    for i in range(total_frames):
        # Calculate the vertical offset for scrolling
        offset = int((i / total_frames) * (img_height - height))
        frame = image[offset : offset + height, :, :]
        out.write(frame)

    out.release()


###bs for adding captions over videos


from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import time
import os


def render_caption_frame(
    frame_size: tuple,
    words: list[str],
    highlight_index: int,
    font_path: str = r"fonts\SourGummy-Bold.ttf",
    max_line_length: int = 10,  # Wrap after this many characters
    save: bool = False,
) -> Image.Image:

    start_time = time.time()

    font_size = 132  # Doubled from original
    stroke_width = 6
    spacing = 24

    regular_fill = (255, 255, 255, 255)
    regular_outline = (0, 102, 255, 255)
    highlight_fill = (255, 255, 0, 255)
    highlight_outline = (255, 0, 0, 255)

    # Load font
    font = ImageFont.truetype(font_path, font_size)

    # Create base transparent image
    img = Image.new("RGBA", frame_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # --- Word wrapping ---
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        word_len = len(word) + 1  # +1 for space
        if current_len + word_len > max_line_length and current_line:
            lines.append(current_line)
            current_line = [word]
            current_len = word_len
        else:
            current_line.append(word)
            current_len += word_len
    if current_line:
        lines.append(current_line)

    # --- Vertical centering ---
    total_text_height = len(lines) * font_size + (len(lines) - 1) * spacing
    y = max((frame_size[1] - total_text_height) // 2, 0)

    word_index = 0
    for line in lines:
        line_width = sum(
            draw.textlength(word + " ", font=font) + spacing for word in line
        )
        x = max((frame_size[0] - line_width) // 2, 0)

        for word in line:
            fill = highlight_fill if word_index == highlight_index else regular_fill
            outline = (
                highlight_outline if word_index == highlight_index else regular_outline
            )

            draw.text(
                (x, y),
                word,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=outline,
            )
            x += int(draw.textlength(word + " ", font=font) + spacing)
            word_index += 1

        y += font_size + spacing

    print(f"🖼️ Rendered caption frame in {time.time() - start_time:.2f} seconds")

    if save:
        os.makedirs("temp", exist_ok=True)
        path = f"temp/{len(os.listdir('temp'))}_caption_frame.png"
        img.save(path)
        print(f"📦 Caption frame saved as {path}")
        return path

    return img


from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
from PIL import Image
import numpy as np
import time


def overlay_images_onto_video(
    video_path: str,
    frames: list,
    out_video_path: str = "captioned_output.mp4",
) -> str:
    """
    Overlays multiple image frames onto a video at specified times.

    Args:
        video_path (str): Path to the input video.
        frames (list): List of dicts with keys: 'frame_path', 'start_time', 'end_time'.
        out_video_path (str): Path to save the output video.

    Returns:
        str: Path to the saved output video.
    """
    t0 = time.time()

    # Load base video
    video = VideoFileClip(video_path)
    image_clips = []

    try:
        for frame_info in frames:
            path = frame_info["frame_path"]
            start = frame_info["start_time"]
            end = frame_info["end_time"]

            # Load and convert image to array
            img = Image.open(path).convert("RGBA")
            img_array = np.array(img)

            img_clip = (
                ImageClip(img_array, ismask=False)
                .set_start(start)
                .set_end(end)
                .set_position(("center", "bottom"))
            )
            image_clips.append(img_clip)

        # Combine video with all image clips
        final = CompositeVideoClip([video] + image_clips)
        final.write_videofile(out_video_path, codec="libx264", audio_codec="aac", logger=None)
    finally:
        video.close()

    print(
        f"Overlayed {len(frames)} frames onto video in {time.time() - t0:.2f} seconds"
    )
    return out_video_path


def overlay_image_onto_video(
    video_path: str,
    frame_path: str,
    start_time: float,
    end_time: float,
    out_video_path: str = "captioned_output.mp4",
) -> str:
    t0 = time.time()

    # Load the video
    video = VideoFileClip(video_path)

    try:
        # Load the caption frame image from disk
        frame = Image.open(frame_path).convert("RGBA")
        frame_array = np.array(frame)

        # Create image clip for the caption
        img_clip = (
            ImageClip(frame_array, ismask=False)
            .set_start(start_time)
            .set_end(end_time)
            .set_position(("center", "bottom"))
        )

        # Combine original video and the image clip
        composite = CompositeVideoClip([video, img_clip])
        composite.write_videofile(out_video_path, codec="libx264", audio_codec="aac", logger=None)
    finally:
        video.close()

    print(f"Overlayed frame onto video in {time.time() - t0:.2f} seconds")
    return out_video_path


def caption_video(video_path, caption_frames, out_video_path):
    # compile caption_frames data into a list of dicts with frame_path, start_time, end_time
    frame_datums = []
    video_dims = get_video_dims(video_path)
    for caption_frame in caption_frames:
        words = caption_frame["words"]
        highlight_index = caption_frame["highlight_index"]
        start_time = caption_frame["start_time"]
        end_time = caption_frame["end_time"]
        frame_path = render_caption_frame(
            video_dims,
            words,
            highlight_index,
            save=True,
        )
        frame_datum = {
            "frame_path": frame_path,
            "start_time": start_time,
            "end_time": end_time,
        }
        frame_datums.append(frame_datum)

    # use that to batch overlay images onto video
    overlay_images_onto_video(
        video_path,
        frame_datums,
        out_video_path,
    )

    def clear_temp_frame_images(frame_datums):
        for frame_datum in frame_datums:
            frame_path = frame_datum["frame_path"]
            if os.path.exists(frame_path):
                os.remove(frame_path)
                print(f"Removed temporary frame image: {frame_path}")

    clear_temp_frame_images(frame_datums)


if __name__ == "__main__":
    folder = r'H:\my_files\my_programs\shortform-sludge-maker\final_vids'
    for f in os.listdir(folder):
        for file in os.listdir(os.path.join(folder, f)):
            if file.endswith('.mp4'):
                video_path = os.path.join(folder, f, file)
                duration = get_video_duration(video_path)
                print(f"Video: {file}, Duration: {duration:.2f} seconds")
