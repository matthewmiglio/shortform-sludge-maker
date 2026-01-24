"""
End-to-end test for the final_vid production pipeline.
Generates one video, verifies it was created, then cleans up.
Does NOT write to post_usage_history or youtube_post_history.
"""
import sys
import os
import shutil
import time
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

FINAL_VIDS_DIR = os.path.join(PROJECT_ROOT, "final_vids")
TEMP_DIR = os.path.join(PROJECT_ROOT, "temp")
REDDIT_DATA_DIR = os.path.join(PROJECT_ROOT, "reddit_data")


def main():
    results = []

    def run_step(name, fn):
        t = time.time()
        try:
            fn()
            results.append((name, "OK", time.time() - t))
        except Exception as e:
            results.append((name, f"FAIL: {e}", time.time() - t))
            raise

    # Suppress pipeline stdout noise
    real_stdout = sys.stdout

    print("\n  FINAL VID PIPELINE - END TO END TEST")
    print("  Running...\n")

    new_vid_path = None

    try:
        # Step 1
        def check_posts():
            json_files = [f for f in os.listdir(REDDIT_DATA_DIR) if f.endswith(".json")]
            if not json_files:
                raise Exception("No posts in reddit_data/")
        run_step("Check posts exist", check_posts)

        # Step 2
        os.makedirs(FINAL_VIDS_DIR, exist_ok=True)
        existing_vids = set(os.listdir(FINAL_VIDS_DIR))

        def record_state():
            pass
        run_step("Record final_vids state", record_state)

        # Step 3
        import video_maker

        class FakePostUsageHistory:
            def __init__(self): pass
            def add_post(self, url): pass
            def post_exists(self, url): return False
            def get_all_posts(self): return []

        def patch_history():
            video_maker.PostUsageHistory = FakePostUsageHistory
        run_step("Patch PostUsageHistory", patch_history)

        # Step 4
        result_data = {}
        def create_video():
            sys.stdout = io.StringIO()
            try:
                result = video_maker.create_stacked_reddit_scroll_video(FINAL_VIDS_DIR)
            finally:
                sys.stdout = real_stdout
            if result is False or result is None:
                raise Exception("No usable posts")
            result_data["video"], result_data["post"] = result
        run_step("Create video", create_video)

        # Step 5
        def gen_metadata():
            sys.stdout = io.StringIO()
            try:
                result_data["metadata"] = video_maker.create_metadata(
                    result_data["post"]["title"],
                    result_data["post"]["content"],
                    result_data["post"].get("url"),
                )
                scores = result_data["post"].get("scores")
                if scores:
                    result_data["metadata"].update(scores)
            finally:
                sys.stdout = real_stdout
        run_step("Generate metadata", gen_metadata)

        # Step 6
        def compile_vid():
            sys.stdout = io.StringIO()
            try:
                video_maker.compile_video_and_metadata(
                    result_data["video"], result_data["metadata"], FINAL_VIDS_DIR
                )
            finally:
                sys.stdout = real_stdout
        run_step("Compile final_vid", compile_vid)

        # Step 7
        def verify_output():
            nonlocal new_vid_path
            current_vids = set(os.listdir(FINAL_VIDS_DIR))
            new_vids = current_vids - existing_vids
            if not new_vids:
                raise Exception("No new folder created")
            folder = new_vids.pop()
            new_vid_path = os.path.join(FINAL_VIDS_DIR, folder)
            if not os.path.exists(os.path.join(new_vid_path, "video.mp4")):
                raise Exception("video.mp4 missing")
            if not os.path.exists(os.path.join(new_vid_path, "metadata.json")):
                raise Exception("metadata.json missing")
        run_step("Verify output", verify_output)

        # Step 8
        def clean_temp():
            sys.stdout = io.StringIO()
            try:
                video_maker.cleanup_temp_files()
            finally:
                sys.stdout = real_stdout
            temp_files = os.listdir(TEMP_DIR) if os.path.exists(TEMP_DIR) else []
            if temp_files:
                raise Exception(f"{len(temp_files)} files remain")
        run_step("Clean temp/", clean_temp)

        # Step 9
        def delete_test_vid():
            if new_vid_path and os.path.exists(new_vid_path):
                shutil.rmtree(new_vid_path)
                if os.path.exists(new_vid_path):
                    raise Exception("Delete failed")
        run_step("Delete test video", delete_test_vid)

    except Exception:
        pass

    # Print table
    print("  " + "-" * 56)
    print(f"  {'#':<4}{'Step':<28}{'Result':<10}{'Time':>8}")
    print("  " + "-" * 56)
    for i, (name, status, elapsed) in enumerate(results, 1):
        status_short = "OK" if status == "OK" else "FAIL"
        print(f"  {i:<4}{name:<28}{status_short:<10}{elapsed:>7.1f}s")
    print("  " + "-" * 56)

    total = sum(r[2] for r in results)
    all_ok = all(r[1] == "OK" for r in results)
    status_msg = "ALL PASSED" if all_ok else "FAILED"
    print(f"  {'':<4}{'Total':<28}{status_msg:<10}{total:>7.1f}s")
    print("  " + "-" * 56 + "\n")


if __name__ == "__main__":
    main()
