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

DESCRIPTION_PROMPT = """Write a 2-3 sentence YouTube Shorts description with a hook and 3-5 relevant hashtags for this Reddit story. Only output the description, nothing else.

Reddit story:
{text}

Description:"""


def _format_prompt(prompt_template: str, text: str) -> str:
    """Format prompt for Qwen model using ChatML format."""
    prompt_text = prompt_template.format(text=text[:1500])
    return f"<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"


def _clean_output(text: str) -> str:
    """Clean up model output."""
    text = text.strip()
    # Remove quotes
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    # Remove prefix labels
    text = re.sub(r'^(Title|Description):\s*', '', text, flags=re.IGNORECASE)
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

    description = _clean_output(generated)
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
