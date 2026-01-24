import json
import urllib.request


OLLAMA_URL = "http://localhost:11434/api/generate"
SCORING_MODEL = "gemma2:9b"
SCORING_PROMPT = """Score this Reddit post for YouTube Shorts reposting potential.
Output a JSON object with exactly these three integer fields (1-10 each):

- "engagement": How controversial, dramatic, or attention-grabbing is this post? (1=boring/mundane, 10=extremely dramatic/spicy/hot-take)
- "sentiment": How emotionally charged is the writing? (1=calm/neutral/measured, 10=outraged/furious/explosive)
- "repost_quality": How much substantive first-person content is there to narrate in a video?
  1-3: no real content (link-only, podcast promo, one-liner, health tip, TV recommendation, or pure spam)
  4-5: very brief or vagueing personal content, or entirely second-hand/abstract
  6-7: decent first-person content with personal details and some situation described
  8-9: rich first-person narrative with detailed personal situation, conflict or drama, and emotional weight
  10: exceptional story - detailed, dramatic, emotionally compelling, with clear stakes

Output ONLY valid JSON, nothing else.

Reddit post title: {title}
Reddit post content: {content}"""

MIN_ENGAGEMENT = 5
MIN_REPOST_QUALITY = 6


def score_post(title, content):
    """Score a post using Ollama. Returns dict with scores or None on failure."""
    prompt = SCORING_PROMPT.format(title=title, content=content[:1500])
    payload = json.dumps({
        "model": SCORING_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_gpu": 0},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            scores = json.loads(result["response"])
            return {
                "engagement": max(1, min(10, int(scores.get("engagement", 5)))),
                "sentiment": max(1, min(10, int(scores.get("sentiment", 5)))),
                "repost_quality": max(1, min(10, int(scores.get("repost_quality", 5)))),
            }
    except Exception as e:
        print(f"Scoring failed: {e}")
        return None
