#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "zai-sdk",
#     "httpx",
# ]
# ///

"""
Generate AI videos using Z.AI video models via official SDK.

Supported Models:
    - CogVideoX-3: Best quality, concurrency=1, text/image/frame-transition
    - ViduQ1-text: Text-to-video, concurrency=5
    - ViduQ1-Image: Image-to-video, concurrency=5
    - ViduQ1-Start-End: Frame transitions, concurrency=5
    - Vidu2-Image: Image-to-video alternative, concurrency=5
    - Vidu2-Start-End: Frame transitions alternative, concurrency=5
    - Vidu2-Reference: Reference-guided video, concurrency=5

Usage:
    # Text to video (CogVideoX-3)
    uv run generate_video.py --prompt "A cat playing with a ball" --output video.mp4

    # Text to video (ViduQ1 - higher concurrency)
    uv run generate_video.py --model viduq1-text --prompt "A cat playing" --output video.mp4

    # Image to video
    uv run generate_video.py --model viduq1-image --prompt "Make it move" --image-url "https://..." --output video.mp4

    # Start/End frames transition
    uv run generate_video.py --model viduq1-start-end --prompt "Smooth transition" --image-url "https://start.jpg" "https://end.jpg" --output video.mp4

Environment: Z_AI_API_KEY must be set.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import httpx
from pathlib import Path
from zai import ZaiClient

# Available models with their capabilities and rate limits
MODELS = {
    "cogvideox-3": {
        "name": "CogVideoX-3",
        "concurrency": 1,
        "supports": ["text", "image", "start-end"],
        "description": "Best quality, limited concurrency",
    },
    "viduq1-text": {
        "name": "ViduQ1-text",
        "concurrency": 5,
        "supports": ["text"],
        "description": "Text-to-video, higher concurrency",
    },
    "viduq1-image": {
        "name": "ViduQ1-Image",
        "concurrency": 5,
        "supports": ["image"],
        "description": "Image-to-video, higher concurrency",
    },
    "viduq1-start-end": {
        "name": "ViduQ1-Start-End",
        "concurrency": 5,
        "supports": ["start-end"],
        "description": "Frame transitions, higher concurrency",
    },
    "vidu2-image": {
        "name": "Vidu2-Image",
        "concurrency": 5,
        "supports": ["image"],
        "description": "Image-to-video alternative",
    },
    "vidu2-start-end": {
        "name": "Vidu2-Start-End",
        "concurrency": 5,
        "supports": ["start-end"],
        "description": "Frame transitions alternative",
    },
    "vidu2-reference": {
        "name": "Vidu2-Reference",
        "concurrency": 5,
        "supports": ["reference"],
        "description": "Reference-guided video",
    },
}


def get_model_type(image_url):
    """Determine the appropriate model type based on inputs."""
    if image_url is None:
        return "text"
    elif isinstance(image_url, list) and len(image_url) >= 2:
        return "start-end"
    elif image_url:
        return "image"
    return "text"


def get_cache_key(prompt: str, model: str, **kwargs) -> str:
    """Generate a cache key from generation parameters."""
    cache_data = {
        "prompt": prompt,
        "model": model,
        "image_url": kwargs.get("image_url"),
        "size": kwargs.get("size"),
        "fps": kwargs.get("fps"),
        "duration": kwargs.get("duration"),
        "quality": kwargs.get("quality"),
    }
    cache_str = json.dumps(cache_data, sort_keys=True)
    return hashlib.md5(cache_str.encode()).hexdigest()


def get_cache_path(cache_key: str) -> str:
    """Get the cache file path for a given key."""
    cache_dir = Path.home() / ".cache" / "media-producer" / "video-tasks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.json"


def load_task_cache(cache_key: str) -> dict | None:
    """Load cached task info if exists."""
    cache_path = get_cache_path(cache_key)
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return None


def save_task_cache(cache_key: str, task_id: str, prompt: str):
    """Save task info to cache."""
    cache_path = get_cache_path(cache_key)
    cache_path.write_text(json.dumps({
        "task_id": task_id,
        "prompt": prompt,
        "created_at": time.time(),
    }))


def generate_video(
    prompt: str,
    output: str,
    model: str = "cogvideox-3",
    image_url: str | list | None = None,
    quality: str = "quality",
    with_audio: bool = True,
    size: str = "1920x1080",
    fps: int = 30,
    duration: int = 5,
    poll_interval: int = 5,
    force: bool = False,
):
    """Generate a video using the specified model via Z.AI SDK.

    Features:
    - Skip if output file already exists (unless --force)
    - Recovery from cached task_id if generation was interrupted
    - Saves task_id to cache for recovery
    """
    # 1. Check if output already exists
    if os.path.exists(output) and not force:
        print(f"[CACHE] Output already exists: {output}")
        print("Use --force to regenerate")
        return {"status": "cached", "path": output}

    api_key = os.environ.get("Z_AI_API_KEY")
    if not api_key:
        print("Error: Z_AI_API_KEY environment variable not set")
        sys.exit(1)

    # Validate model
    model_key = model.lower()
    if model_key not in MODELS:
        print(f"Error: Unknown model '{model}'")
        print(f"Available models: {', '.join(MODELS.keys())}")
        sys.exit(1)

    model_info = MODELS[model_key]
    model_name = model_info["name"]

    # Validate model supports the requested operation
    model_type = get_model_type(image_url)
    if model_type not in model_info["supports"]:
        print(f"Error: Model '{model_name}' does not support {model_type} mode")
        print(f"Supported modes: {', '.join(model_info['supports'])}")
        sys.exit(1)

    print(f"Model: {model_name} (concurrency: {model_info['concurrency']})")
    print(f"Mode: {model_type}")

    # Calculate cache key for recovery
    cache_key = get_cache_key(
        prompt=prompt,
        model=model,
        image_url=image_url,
        size=size,
        fps=fps,
        duration=duration,
        quality=quality,
    )

    # 2. Check for cached task_id (recovery from interrupted generation)
    cached_task = load_task_cache(cache_key)
    if cached_task:
        print(f"[RECOVERY] Found cached task: {cached_task['task_id']}")
        print("[RECOVERY] Attempting to retrieve result...")

    # Initialize SDK client
    client = ZaiClient(api_key=api_key)

    # Build kwargs for SDK call
    kwargs = {
        "model": model_name,
        "prompt": prompt,
        "quality": quality,
        "with_audio": with_audio,
        "size": size,
        "fps": fps,
        "duration": duration,
    }

    # Add image URLs if provided
    if image_url:
        if isinstance(image_url, list):
            kwargs["image_url"] = image_url
        else:
            kwargs["image_url"] = [image_url]

    # 3. Try recovery from cached task first
    task_id = None
    if cached_task:
        task_id = cached_task["task_id"]
        try:
            result = client.videos.retrieve_videos_result(id=task_id)
            status = getattr(result, 'task_status', 'UNKNOWN')

            if status == "SUCCESS":
                print("[RECOVERY] Task completed! Downloading...")
                video_result = getattr(result, 'video_result', None)
                if video_result and len(video_result) > 0:
                    video_url = getattr(video_result[0], 'url', None)
                    if video_url:
                        with httpx.Client(timeout=120) as http_client:
                            video_resp = http_client.get(video_url)
                            video_resp.raise_for_status()
                            with open(output, "wb") as f:
                                f.write(video_resp.content)
                        print(f"[RECOVERY] Video saved to: {output}")
                        return result
            elif status == "FAIL":
                print("[RECOVERY] Previous task failed. Will generate new...")
                task_id = None
            else:
                print(f"[RECOVERY] Task still {status}. Resuming polling...")
        except Exception as e:
            print(f"[RECOVERY] Failed to recover: {e}")
            task_id = None

    # 4. If no recovery, submit new generation request
    if not task_id:
        print("Submitting generation request...")
        response = client.videos.generations(**kwargs)
        task_id = response.id

        # 5. Save task_id to cache for potential recovery
        save_task_cache(cache_key, task_id, prompt)
        print(f"Task submitted: {task_id}")
        print(f"Initial status: {getattr(response, 'task_status', 'PROCESSING')}")

    # Poll for result
    while True:
        time.sleep(poll_interval)
        result = client.videos.retrieve_videos_result(id=task_id)

        status = getattr(result, 'task_status', 'PROCESSING')
        print(f"Status: {status}")

        if status == "SUCCESS":
            # A resposta tem video_result (lista) com url dentro
            video_result = getattr(result, 'video_result', None)

            video_url = None
            if video_result and len(video_result) > 0:
                video_url = getattr(video_result[0], 'url', None)

            # Fallback: tentar video_url direto
            if not video_url:
                video_url = getattr(result, 'video_url', None)

            if video_url:
                # Download video
                print(f"Downloading video from: {video_url}")
                with httpx.Client(timeout=120) as http_client:
                    video_resp = http_client.get(video_url)
                    video_resp.raise_for_status()
                    with open(output, "wb") as f:
                        f.write(video_resp.content)
                print(f"Video saved to: {output}")
            else:
                print(f"Warning: No video_url in success response")
            return result
        elif status == "FAIL":
            error_msg = getattr(result, 'error', 'Unknown error')
            print(f"Generation failed: {error_msg}")
            sys.exit(1)


def list_models():
    """Print available models and their capabilities."""
    print("Available Video Models:\n")
    print(f"{'Model':<20} {'Concurrency':<12} {'Supports':<30} Description")
    print("-" * 90)
    for key, info in MODELS.items():
        supports = ", ".join(info["supports"])
        print(f"{key:<20} {info['concurrency']:<12} {supports:<30} {info['description']}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate AI videos with Z.AI video models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Text to video with best quality
  uv run generate_video.py --prompt "A cat playing" --output video.mp4

  # Text to video with higher concurrency
  uv run generate_video.py --model viduq1-text --prompt "A sunset" --output video.mp4

  # Image to video
  uv run generate_video.py --model viduq1-image --prompt "Animate this" --image-url "https://..." --output video.mp4

  # Frame transition
  uv run generate_video.py --model viduq1-start-end --prompt "Transform" --image-url "URL1" "URL2" --output video.mp4
        """,
    )
    parser.add_argument("--prompt", help="Text description (required unless --list-models)")
    parser.add_argument(
        "--model",
        default="cogvideox-3",
        choices=list(MODELS.keys()),
        help="Video model to use (default: cogvideox-3)",
    )
    parser.add_argument(
        "--image-url",
        nargs="+",
        help="Image URL(s) for image-to-video or frame transition",
    )
    parser.add_argument("--output", default="output.mp4", help="Output video path")
    parser.add_argument("--quality", choices=["quality", "speed"], default="quality")
    parser.add_argument("--size", default="1920x1080", help="Video resolution")
    parser.add_argument("--fps", type=int, choices=[30, 60], default=30)
    parser.add_argument("--duration", type=int, choices=[5, 10], default=5)
    parser.add_argument("--no-audio", action="store_true", help="Disable audio generation")
    parser.add_argument("--poll-interval", type=int, default=5, help="Seconds between status checks")
    parser.add_argument("--list-models", action="store_true", help="List available models")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if output exists")

    args = parser.parse_args()

    if args.list_models:
        list_models()
        return

    if not args.prompt:
        parser.error("--prompt is required when not using --list-models")

    # Normalize image_url
    if args.image_url is None:
        image_url = None
    elif len(args.image_url) == 1:
        image_url = args.image_url[0]
    else:
        image_url = args.image_url

    generate_video(
        prompt=args.prompt,
        output=args.output,
        model=args.model,
        image_url=image_url,
        quality=args.quality,
        with_audio=not args.no_audio,
        size=args.size,
        fps=args.fps,
        duration=args.duration,
        poll_interval=args.poll_interval,
        force=args.force,
    )


if __name__ == "__main__":
    main()
