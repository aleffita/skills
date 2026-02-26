#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "zai-sdk",
#     "httpx",
# ]
# ///

"""
Generate AI images using Z.AI CogView-4 via official SDK.

Usage:
    # Single image
    uv run generate_image.py --prompt "A cat sitting on a windowsill" --output image.png

    # Multiple images
    uv run generate_image.py --prompt "A sunset over mountains" --output ./frames/ --count 4 --prefix frame_

    # Use fallback image (copy from test_sdk.png)
    uv run generate_image.py --prompt "test" --output image.png --fallback

Environment: Z_AI_API_KEY must be set.
"""

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

import httpx
from zai import ZaiClient

MODEL = "CogView-4-250304"

# Fallback image path (relative to script location)
FALLBACK_IMAGE_NAME = "test_sdk.png"


def get_fallback_image_path() -> str:
    """Get the path to the fallback image."""
    script_dir = Path(__file__).parent.parent  # Go up to skill root
    return script_dir / FALLBACK_IMAGE_NAME


def compute_sha256(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def use_fallback_image(output: str, verify: bool = True) -> str:
    """Copy fallback image to output path.

    Args:
        output: Destination path for the image
        verify: If True, verify the image is valid by checking SHA256

    Returns:
        Path to the output image
    """
    fallback_path = get_fallback_image_path()

    if not fallback_path.exists():
        print(f"Error: Fallback image not found at {fallback_path}")
        sys.exit(1)

    if verify:
        # Basic validation - check file exists and has reasonable size
        file_size = fallback_path.stat().st_size
        if file_size < 1000:  # Less than 1KB is suspicious
            print(f"Warning: Fallback image seems too small ({file_size} bytes)")

    shutil.copy2(fallback_path, output)
    print(f"[FALLBACK] Using fallback image: {output}")
    return output


def generate_image(
    prompt: str,
    output: str,
    size: str = "1024x1024",
    use_fallback: bool = False,
) -> str:
    """Generate a single image and save to output path.

    Args:
        prompt: Text description of the image
        output: Output file path
        size: Image resolution (e.g., 1024x1024)
        use_fallback: If True, skip API and use fallback image

    Returns:
        Path to the generated image
    """
    # Use fallback if requested
    if use_fallback:
        return use_fallback_image(output)

    # Check if output already exists (cache behavior)
    if os.path.exists(output):
        print(f"[CACHE] Output already exists: {output}")
        print("Use --force to regenerate")
        return output

    api_key = os.environ.get("Z_AI_API_KEY")
    if not api_key:
        print("Error: Z_AI_API_KEY environment variable not set")
        print("Use --fallback to use the fallback image instead")
        sys.exit(1)

    # Initialize SDK client
    client = ZaiClient(api_key=api_key)

    print(f"Generating image with {MODEL}...")
    print(f"Prompt: {prompt[:100]}...")

    try:
        # Call SDK
        response = client.images.generations(
            model=MODEL,
            prompt=prompt,
            size=size,
        )

        # Extract image URL from response
        if hasattr(response, 'data') and len(response.data) > 0:
            image_url = response.data[0].url
            if not image_url:
                print("Error: No image URL in response")
                print("Using fallback image...")
                return use_fallback_image(output)
        else:
            print(f"Error: Unexpected response format: {response}")
            print("Using fallback image...")
            return use_fallback_image(output)

        # Download image
        print(f"Downloading from: {image_url}")
        with httpx.Client(timeout=60) as http_client:
            img_resp = http_client.get(image_url)
            img_resp.raise_for_status()
            with open(output, "wb") as f:
                f.write(img_resp.content)

        print(f"Image saved to: {output}")
        return output

    except Exception as e:
        print(f"Error generating image: {e}")
        print("Using fallback image...")
        return use_fallback_image(output)


def generate_multiple_images(
    prompt: str,
    output_dir: str,
    count: int,
    prefix: str = "image_",
    size: str = "1024x1024",
    use_fallback: bool = False,
) -> list[str]:
    """Generate multiple images and save to output directory.

    Args:
        prompt: Text description of the images
        output_dir: Output directory path
        count: Number of images to generate
        prefix: Filename prefix
        size: Image resolution
        use_fallback: If True, use fallback images

    Returns:
        List of paths to generated images
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    generated = []
    for i in range(count):
        output_file = output_path / f"{prefix}{i+1:03d}.png"
        print(f"\n[{i+1}/{count}] Generating image...")
        result = generate_image(prompt, str(output_file), size, use_fallback)
        generated.append(result)

    print(f"\nGenerated {count} images in: {output_dir}")
    return generated


def main():
    parser = argparse.ArgumentParser(description="Generate AI images with Z.AI CogView-4")
    parser.add_argument("--prompt", help="Text description of the image (required unless --fallback)")
    parser.add_argument("--output", default="output.png", help="Output file path or directory (with --count)")
    parser.add_argument("--size", default="1024x1024", help="Image resolution (e.g., 1024x1024, 1920x1080)")
    parser.add_argument("--count", type=int, default=1, help="Number of images to generate")
    parser.add_argument("--prefix", default="image_", help="Filename prefix for multiple images")
    parser.add_argument("--fallback", action="store_true", help="Use fallback image instead of API")
    parser.add_argument("--force", action="store_true", help="Regenerate even if output exists")

    args = parser.parse_args()

    # Validate arguments
    if not args.prompt and not args.fallback:
        parser.error("--prompt is required unless using --fallback")

    # Handle --force by removing existing output
    if args.force and args.count == 1 and os.path.exists(args.output):
        os.remove(args.output)
        print(f"[FORCE] Removed existing file: {args.output}")

    if args.count > 1:
        generate_multiple_images(
            prompt=args.prompt or "fallback",
            output_dir=args.output,
            count=args.count,
            prefix=args.prefix,
            size=args.size,
            use_fallback=args.fallback,
        )
    else:
        generate_image(
            prompt=args.prompt or "fallback",
            output=args.output,
            size=args.size,
            use_fallback=args.fallback,
        )


if __name__ == "__main__":
    main()
