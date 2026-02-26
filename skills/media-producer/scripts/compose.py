#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Compose multiple videos into a final output using FFmpeg.

Usage:
    # Concatenate videos from a project
    uv run compose.py --project ./my_project/ --output final.mp4

    # Concatenate specific videos
    uv run compose.py --inputs scene1.mp4 scene2.mp4 scene3.mp4 --output final.mp4

    # With transitions
    uv run compose.py --inputs *.mp4 --output final.mp4 --transition fade --transition-duration 0.5

    # Add text overlay
    uv run compose.py --inputs video.mp4 --output final.mp4 --title "My Video" --title-duration 3

Requirements:
    - FFmpeg must be installed and available in PATH
"""

import argparse
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def check_ffmpeg():
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_project_videos(project_path: str) -> list[str]:
    """Get list of video files from a project, ordered by scene sequence."""
    db_path = os.path.join(project_path, "project.db")
    if not os.path.exists(db_path):
        print(f"Error: No project database at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT output_path FROM scenes WHERE output_path IS NOT NULL AND status = 'completed' ORDER BY sequence"
    ).fetchall()
    conn.close()

    videos = []
    for row in rows:
        path = row["output_path"]
        if os.path.isabs(path):
            videos.append(path)
        else:
            # Relative to project path
            full_path = os.path.join(project_path, path)
            videos.append(full_path)

    return videos


def get_video_info(video_path: str) -> dict:
    """Get video information using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def concatenate_simple(videos: list[str], output: str):
    """Simple concatenation without transitions."""
    print(f"Concatenating {len(videos)} videos...")

    # Create concat file with absolute paths
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for video in videos:
            # Convert to absolute path
            abs_path = os.path.abspath(video)
            # Escape single quotes in path
            escaped = abs_path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            sys.exit(1)
        print(f"Output saved to: {output}")
    finally:
        os.unlink(concat_file)


def concatenate_with_transition(videos: list[str], output: str, transition: str, duration: float):
    """Concatenate with transitions between videos."""
    print(f"Concatenating {len(videos)} videos with {transition} transition ({duration}s)...")

    if len(videos) == 1:
        # Just copy the single video
        subprocess.run(["ffmpeg", "-y", "-i", videos[0], "-c", "copy", output], check=True)
        print(f"Output saved to: {output}")
        return

    # Build complex filter for transitions
    # For simplicity, use xfade filter for crossfade transitions
    inputs = []
    filter_parts = []

    for i, video in enumerate(videos):
        # Convert to absolute path
        abs_path = os.path.abspath(video)
        inputs.extend(["-i", abs_path])

    # Get video info for timing
    total_duration = 0
    video_durations = []
    for video in videos:
        info = get_video_info(video)
        if info and "format" in info:
            dur = float(info["format"].get("duration", 0))
            video_durations.append(dur)
        else:
            video_durations.append(5)  # Default

    # Build xfade chain
    if transition == "fade" or transition == "crossfade":
        # Use xfade filter
        current_input = "[0:v]"
        current_time = video_durations[0] - duration

        for i in range(1, len(videos)):
            next_input = f"[{i}:v]"
            output_label = f"[v{i}]"

            filter_parts.append(
                f"{current_input}{next_input}xfade=transition=fade:duration={duration}:offset={current_time:.2f}{output_label}"
            )
            current_input = output_label
            current_time += video_durations[i] - duration

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg",
            "-y",
        ]
        cmd.extend(inputs)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", current_input,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            output,
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            # Fallback to simple concat
            print("Falling back to simple concatenation...")
            concatenate_simple(videos, output)
        else:
            print(f"Output saved to: {output}")
    else:
        # Unsupported transition, use simple
        print(f"Transition '{transition}' not supported, using simple concatenation")
        concatenate_simple(videos, output)


def add_title(video: str, output: str, title: str, duration: float, fontsize: int = 48):
    """Add text overlay to video."""
    print(f"Adding title: '{title}' ({duration}s)...")

    # Escape special characters for drawtext
    escaped_title = title.replace(":", "\\:").replace("'", "\\'")

    filter_complex = f"drawtext=text='{escaped_title}':fontsize={fontsize}:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,{duration})'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-vf", filter_complex,
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "medium",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        sys.exit(1)
    print(f"Output saved to: {output}")


def scale_video(video: str, output: str, resolution: str):
    """Scale video to target resolution."""
    print(f"Scaling to {resolution}...")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-vf", f"scale={resolution.replace('x', ':')}:force_original_aspect_ratio=decrease,pad={resolution.replace('x', ':')}:(ow-iw)/2:(oh-ih)/2",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "medium",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        sys.exit(1)
    print(f"Output saved to: {output}")


def add_audio_track(
    video: str,
    audio: str,
    output: str,
    volume: float = 1.0,
    mode: str = "mix",
    fade_in: float = 0,
    fade_out: float = 0,
):
    """Add an audio track to a video.

    Args:
        video: Input video file
        audio: Audio file to add
        output: Output video file
        volume: Audio volume (0.0-1.0)
        mode: 'mix' to combine with existing audio, 'replace' to replace
        fade_in: Fade in duration in seconds
        fade_out: Fade out duration in seconds
    """
    print(f"Adding audio track: {audio}")
    print(f"  Volume: {volume}, Mode: {mode}")

    # Build audio filter
    audio_filters = []

    # Apply volume
    if volume != 1.0:
        audio_filters.append(f"volume={volume}")

    # Apply fade effects
    if fade_in > 0:
        audio_filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        # Get video duration for fade out
        info = get_video_info(video)
        if info and "format" in info:
            duration = float(info["format"].get("duration", 0))
            if duration > fade_out:
                audio_filters.append(f"afade=t=out:st={duration - fade_out}:d={fade_out}")

    if mode == "mix":
        # Mix new audio with existing video audio
        filter_complex = f"[0:a]{','.join(audio_filters) if audio_filters else 'anull'}[a1];[1:a]volume={volume}[a2];[a1][a2]amix=inputs=2:duration=first[aout]"
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video,
            "-i", audio,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output,
        ]
    else:  # replace
        # Replace audio track entirely
        audio_filter = ','.join(audio_filters) if audio_filters else 'anull'
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video,
            "-i", audio,
            "-filter_complex", f"[1:a]{audio_filter}[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        sys.exit(1)
    print(f"Output saved to: {output}")


def add_image_overlay(
    video: str,
    image: str,
    output: str,
    position: str = "center",
    duration: float = None,
    opacity: float = 1.0,
    start_time: float = 0,
):
    """Add an image overlay to a video.

    Args:
        video: Input video file
        image: Image file to overlay
        output: Output video file
        position: Position (center, top-left, top-right, bottom-left, bottom-right, or x:y)
        duration: How long to show overlay (None = entire video)
        opacity: Image opacity (0.0-1.0)
        start_time: When to start showing overlay
    """
    print(f"Adding image overlay: {image}")
    print(f"  Position: {position}, Opacity: {opacity}, Start: {start_time}s")

    # Parse position
    position_map = {
        "center": "(W-w)/2:(H-h)/2",
        "top-left": "0:0",
        "top-right": "W-w:0",
        "bottom-left": "0:H-h",
        "bottom-right": "W-w:H-h",
        "center-top": "(W-w)/2:0",
        "center-bottom": "(W-w)/2:H-h",
    }

    if position in position_map:
        overlay_pos = position_map[position]
    elif ":" in position:
        overlay_pos = position
    else:
        overlay_pos = "(W-w)/2:(H-h)/2"  # Default to center

    # Get video duration if not specified
    if duration is None:
        info = get_video_info(video)
        if info and "format" in info:
            duration = float(info["format"].get("duration", 0))
        else:
            duration = 999999  # Very long duration

    # Build filter
    if opacity < 1.0:
        # Apply opacity using colorchannelmixer
        filter_complex = f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[overlay];[0:v][overlay]overlay={overlay_pos}:enable='between(t,{start_time},{start_time + duration})'[out]"
    else:
        filter_complex = f"[0:v][1:v]overlay={overlay_pos}:enable='between(t,{start_time},{start_time + duration})'[out]"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-i", image,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a?",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "medium",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        sys.exit(1)
    print(f"Output saved to: {output}")


def add_subtitles(video: str, srt_file: str, output: str, style: str = "default"):
    """Add subtitles to a video.

    Args:
        video: Input video file
        srt_file: SRT subtitle file
        output: Output video file
        style: Subtitle style ('default', 'bold', 'large')
    """
    print(f"Adding subtitles: {srt_file}")

    # Build subtitles filter with style
    # Escape special characters in path
    escaped_path = srt_file.replace(":", "\\:").replace("'", "'\\''")

    if style == "default":
        subtitle_filter = f"subtitles='{escaped_path}'"
    elif style == "bold":
        subtitle_filter = f"subtitles='{escaped_path}:force_style='Fontweight=Bold'"
    elif style == "large":
        subtitle_filter = f"subtitles='{escaped_path}':force_style='FontSize=24'"
    else:
        subtitle_filter = f"subtitles='{escaped_path}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video,
        "-vf", subtitle_filter,
        "-c:a", "copy",
        "-c:v", "libx264",
        "-preset", "medium",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}")
        sys.exit(1)
    print(f"Output saved to: {output}")


def get_project_tracks(project_path: str) -> list[dict]:
    """Get list of tracks from project database."""
    db_path = os.path.join(project_path, "project.db")
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tracks ORDER BY layer").fetchall()
    conn.close()

    return [dict(row) for row in rows]


def compose_with_tracks(project_path: str, output: str, base_video: str = None):
    """Compose video using all tracks from project.

    Args:
        project_path: Path to project directory
        output: Output video file
        base_video: Base video file (if None, uses concatenated scenes)
    """
    tracks = get_project_tracks(project_path)

    if not tracks:
        print("No tracks found in project")
        return

    print(f"Composing with {len(tracks)} tracks...")

    # Get base video (concatenated scenes or provided)
    if base_video is None:
        videos = get_project_videos(project_path)
        if not videos:
            print("No videos found in project")
            sys.exit(1)
        # Create temp concatenated video
        temp_base = os.path.join(project_path, ".temp_base.mp4")
        concatenate_simple(videos, temp_base)
        current_input = temp_base
    else:
        current_input = base_video

    # Process each track
    for track in tracks:
        print(f"\nProcessing track: {track['name']} (layer {track['layer']})")

        track_output = os.path.join(project_path, f".temp_track_{track['id']}.mp4")

        if track['type'] == 'audio':
            # Get asset path from metadata or find in assets
            metadata = json.loads(track['metadata'] or '{}')
            audio_path = metadata.get('audio_path')
            if not audio_path:
                print(f"  Warning: No audio path for track {track['name']}")
                continue

            # Resolve path
            if not os.path.isabs(audio_path):
                audio_path = os.path.join(project_path, audio_path)

            add_audio_track(
                video=current_input,
                audio=audio_path,
                output=track_output,
                volume=track['volume'],
                mode='mix',
            )

        elif track['type'] == 'image':
            metadata = json.loads(track['metadata'] or '{}')
            image_path = metadata.get('image_path')
            if not image_path:
                print(f"  Warning: No image path for track {track['name']}")
                continue

            if not os.path.isabs(image_path):
                image_path = os.path.join(project_path, image_path)

            position = f"{track['position_x']}:{track['position_y']}"
            add_image_overlay(
                video=current_input,
                image=image_path,
                output=track_output,
                position=position,
                opacity=track['opacity'],
                start_time=track['start_time'],
                duration=track['duration'],
            )

        elif track['type'] == 'subtitle':
            metadata = json.loads(track['metadata'] or '{}')
            srt_path = metadata.get('srt_path')
            if not srt_path:
                print(f"  Warning: No subtitle path for track {track['name']}")
                continue

            if not os.path.isabs(srt_path):
                srt_path = os.path.join(project_path, srt_path)

            add_subtitles(
                video=current_input,
                srt_file=srt_path,
                output=track_output,
            )
        else:
            print(f"  Warning: Unsupported track type: {track['type']}")
            continue

        # Update current input for next track
        if os.path.exists(track_output):
            if current_input != base_video and current_input != base_video:
                os.unlink(current_input)
            current_input = track_output

    # Move final output
    if current_input != output:
        import shutil
        shutil.move(current_input, output)

    # Cleanup temp files
    for track in tracks:
        temp_file = os.path.join(project_path, f".temp_track_{track['id']}.mp4")
        if os.path.exists(temp_file):
            os.unlink(temp_file)

    temp_base = os.path.join(project_path, ".temp_base.mp4")
    if os.path.exists(temp_base):
        os.unlink(temp_base)

    print(f"\nFinal output: {output}")


def main():
    parser = argparse.ArgumentParser(description="Compose videos using FFmpeg")
    parser.add_argument("--project", "-p", help="Project directory (uses scenes from database)")
    parser.add_argument("--inputs", "-i", nargs="+", help="Input video files")
    parser.add_argument("--output", "-o", required=True, help="Output video file")
    parser.add_argument("--transition", "-t", choices=["fade", "crossfade", "none"], default="none", help="Transition type")
    parser.add_argument("--transition-duration", type=float, default=0.5, help="Transition duration in seconds")
    parser.add_argument("--title", help="Title text to overlay")
    parser.add_argument("--title-duration", type=float, default=3.0, help="Title display duration")
    parser.add_argument("--scale", help="Scale to resolution (e.g., 1920x1080)")

    # Audio options
    parser.add_argument("--add-audio", help="Audio file to add as soundtrack")
    parser.add_argument("--audio-volume", type=float, default=1.0, help="Audio volume (0.0-1.0)")
    parser.add_argument("--audio-mode", choices=["mix", "replace"], default="mix", help="How to handle existing audio")
    parser.add_argument("--audio-fade-in", type=float, default=0, help="Audio fade in duration (seconds)")
    parser.add_argument("--audio-fade-out", type=float, default=0, help="Audio fade out duration (seconds)")

    # Image overlay options
    parser.add_argument("--add-image", help="Image file to overlay")
    parser.add_argument("--image-position", default="center", help="Overlay position (center, top-left, etc.)")
    parser.add_argument("--image-opacity", type=float, default=1.0, help="Image opacity (0.0-1.0)")
    parser.add_argument("--image-duration", type=float, help="How long to show overlay (seconds)")
    parser.add_argument("--image-start", type=float, default=0, help="When to start showing overlay")

    # Subtitle options
    parser.add_argument("--add-subtitles", help="SRT subtitle file to embed")
    parser.add_argument("--subtitle-style", choices=["default", "bold", "large"], default="default")

    # Multi-track composition
    parser.add_argument("--with-tracks", action="store_true", help="Compose using all project tracks")

    args = parser.parse_args()

    # Check FFmpeg
    if not check_ffmpeg():
        print("Error: FFmpeg not found. Please install FFmpeg.")
        sys.exit(1)

    # Multi-track composition mode
    if args.with_tracks and args.project:
        compose_with_tracks(args.project, args.output)
        return

    # Get input videos
    if args.project:
        videos = get_project_videos(args.project)
        if not videos:
            print("No completed videos found in project")
            sys.exit(1)
    elif args.inputs:
        videos = args.inputs
    else:
        print("Error: Either --project or --inputs must be specified")
        sys.exit(1)

    # Verify videos exist
    for video in videos:
        if not os.path.exists(video):
            print(f"Error: Video not found: {video}")
            sys.exit(1)

    # Process
    temp_output = args.output

    if args.transition != "none" and len(videos) > 1:
        temp_output = args.output + ".temp.mp4"
        concatenate_with_transition(videos, temp_output, args.transition, args.transition_duration)
    else:
        concatenate_simple(videos, temp_output)

    # Apply additional effects
    current_input = temp_output

    if args.title:
        title_output = args.output + ".title.mp4"
        add_title(current_input, title_output, args.title, args.title_duration)
        if current_input != temp_output:
            os.unlink(current_input)
        current_input = title_output

    # Add audio track
    if args.add_audio:
        if not os.path.exists(args.add_audio):
            print(f"Error: Audio file not found: {args.add_audio}")
            sys.exit(1)
        audio_output = args.output + ".audio.mp4"
        add_audio_track(
            video=current_input,
            audio=args.add_audio,
            output=audio_output,
            volume=args.audio_volume,
            mode=args.audio_mode,
            fade_in=args.audio_fade_in,
            fade_out=args.audio_fade_out,
        )
        if current_input != temp_output:
            os.unlink(current_input)
        current_input = audio_output

    # Add image overlay
    if args.add_image:
        if not os.path.exists(args.add_image):
            print(f"Error: Image file not found: {args.add_image}")
            sys.exit(1)
        image_output = args.output + ".image.mp4"
        add_image_overlay(
            video=current_input,
            image=args.add_image,
            output=image_output,
            position=args.image_position,
            duration=args.image_duration,
            opacity=args.image_opacity,
            start_time=args.image_start,
        )
        if current_input != temp_output:
            os.unlink(current_input)
        current_input = image_output

    # Add subtitles
    if args.add_subtitles:
        if not os.path.exists(args.add_subtitles):
            print(f"Error: Subtitle file not found: {args.add_subtitles}")
            sys.exit(1)
        subtitle_output = args.output + ".subs.mp4"
        add_subtitles(
            video=current_input,
            srt_file=args.add_subtitles,
            output=subtitle_output,
            style=args.subtitle_style,
        )
        if current_input != temp_output:
            os.unlink(current_input)
        current_input = subtitle_output

    if args.scale:
        scale_output = args.output if current_input == args.output else args.output + ".scale.mp4"
        scale_video(current_input, scale_output, args.scale)
        if current_input != args.output and current_input != temp_output:
            os.unlink(current_input)
        current_input = scale_output

    # Rename final output if needed
    if current_input != args.output:
        import shutil
        shutil.move(current_input, args.output)

    # Cleanup temp concat file if it exists
    if temp_output != args.output and os.path.exists(temp_output):
        os.unlink(temp_output)

    print(f"\nFinal output: {args.output}")


if __name__ == "__main__":
    main()
