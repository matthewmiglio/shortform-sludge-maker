"""
Metadata Generator - Generates YouTube titles and descriptions from Reddit posts.

Uses Qwen 2.5 1.5B Instruct for generation.
"""

import re
from typing import Optional, Tuple

# Lazy-loaded model to avoid slow imports on startup
_generator = None


def _get_generator():
    """Lazy load the model only when needed."""
    global _generator
    if _generator is None:
        print("[Metadata] Loading Qwen 2.5 1.5B model...")
        from transformers import pipeline
        import torch

        _generator = pipeline(
            "text-generation",
            model="Qwen/Qwen2.5-1.5B-Instruct",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )
        print("[Metadata] Model loaded successfully!")
    return _generator


TITLE_PROMPT = """Generate a catchy, attention-grabbing YouTube Shorts title (max 10 words) for this Reddit story. Make it emotional and dramatic. Only output the title, nothing else.

Reddit story:
{text}

Title:"""

DESCRIPTION_PROMPT = """Write a YouTube Shorts description for this Reddit story with the following format:
Hook: [1-2 engaging sentences that make viewers want to watch]
Hashtags: [3-5 relevant hashtags]

Only output in that exact format, nothing else.

Reddit story:
{text}

Description:"""


def _format_prompt(prompt_template: str, text: str) -> str:
    """Format prompt for Qwen model using ChatML format."""
    prompt_text = prompt_template.format(text=text[:1500])
    return f"<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"


def _strip_emojis(text: str) -> str:
    """Remove emojis and other non-ASCII special characters."""
    # Remove emoji unicode ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended
        "\U00002600-\U000026FF"  # misc symbols
        "\U00002700-\U000027BF"  # dingbats
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


def _clean_output(text: str, is_description: bool = False) -> str:
    """Clean up model output."""
    text = text.strip()
    # Remove quotes
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    # Remove prefix labels
    text = re.sub(r'^(Title|Description):\s*', '', text, flags=re.IGNORECASE)
    # Strip emojis
    text = _strip_emojis(text)
    # Remove markdown bold formatting (**text** -> text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Remove "Hook:" and "Hashtags:" labels
    text = re.sub(r'^Hook:\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'\nHashtags?:\s*', '\n', text, flags=re.IGNORECASE)
    # Remove text within brackets [like this]
    text = re.sub(r'\[[^\]]*\]', '', text)
    # Remove escaped quotes \"
    text = text.replace('\\"', '')

    if is_description:
        # Preserve newlines for description formatting but clean up extra whitespace
        lines = [re.sub(r'\s+', ' ', line).strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
    else:
        # Clean up any double spaces for titles
        text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_title(post_title: str, post_content: str) -> str:
    """Generate a YouTube title from Reddit post content."""
    generator = _get_generator()

    input_text = f"{post_title}\n\n{post_content}"
    prompt = _format_prompt(TITLE_PROMPT, input_text)

    output = generator(
        prompt,
        max_new_tokens=30,
        temperature=0.2,
        do_sample=True,
        top_p=0.9,
        repetition_penalty=1.2,
        pad_token_id=generator.tokenizer.eos_token_id,
    )

    generated = output[0]["generated_text"]
    if generated.startswith(prompt):
        generated = generated[len(prompt):]

    # Take only first line for title
    title = _clean_output(generated.split("\n")[0])
    return title


def generate_description(post_title: str, post_content: str) -> str:
    """Generate a YouTube description from Reddit post content."""
    generator = _get_generator()

    input_text = f"{post_title}\n\n{post_content}"
    prompt = _format_prompt(DESCRIPTION_PROMPT, input_text)

    output = generator(
        prompt,
        max_new_tokens=100,
        temperature=0.2,
        do_sample=True,
        top_p=0.9,
        repetition_penalty=1.2,
        pad_token_id=generator.tokenizer.eos_token_id,
    )

    generated = output[0]["generated_text"]
    if generated.startswith(prompt):
        generated = generated[len(prompt):]

    description = _clean_output(generated, is_description=True)
    return description


def generate_metadata(post_title: str, post_content: str) -> dict:
    """
    Generate complete YouTube metadata (title + description) from Reddit post.

    Args:
        post_title: The Reddit post title
        post_content: The Reddit post body content

    Returns:
        dict with 'title' and 'description' keys
    """
    print("[Metadata] Generating title...")
    title = generate_title(post_title, post_content)
    print(f"[Metadata] Title: {title}")

    print("[Metadata] Generating description...")
    description = generate_description(post_title, post_content)
    print(f"[Metadata] Description: {description[:80]}...")

    return {
        "title": title,
        "description": description,
    }
