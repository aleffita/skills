#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "zai-sdk",
#     "httpx",
# ]
# ///

"""Retrieve video generation result by task ID using Z.AI SDK.

Usage:
    uv run retrieve_result.py --task-id <id> [--output video.mp4]
"""

import argparse
import os
import sys

import httpx
from zai import ZaiClient


def retrieve_result(task_id: str, output: str | None = None):
    api_key = os.environ.get("Z_AI_API_KEY")
    if not api_key:
        print("Error: Z_AI_API_KEY environment variable not set")
        sys.exit(1)

    # Initialize SDK client
    client = ZaiClient(api_key=api_key)

    # Retrieve result via SDK
    result = client.videos.retrieve_videos_result(id=task_id)

    status = getattr(result, 'task_status', 'UNKNOWN')
    print(f"Status: {status}")

    if status == "SUCCESS":
        video_url = getattr(result, 'video_url', None)
        if video_url:
            print(f"Video URL: {video_url}")
            if output:
                with httpx.Client(timeout=60) as http_client:
                    video_resp = http_client.get(video_url)
                    video_resp.raise_for_status()
                    with open(output, "wb") as f:
                        f.write(video_resp.content)
                print(f"Saved to: {output}")
        else:
            print("No video URL in response")
    elif status == "FAIL":
        error = getattr(result, 'error', 'Unknown error')
        print(f"Generation failed: {error}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output", help="Output file path")
    args = parser.parse_args()

    result = retrieve_result(args.task_id, args.output)
    print(result)


if __name__ == "__main__":
    main()
