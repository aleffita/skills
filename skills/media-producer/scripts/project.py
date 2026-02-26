#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
# ]
# ///

"""
Manage media production projects with SQLite database.

Usage:
    # Initialize a new project
    uv run project.py init "My Project" --output ./my_project/

    # Show project status
    uv run project.py status --project ./my_project/

    # Add a scene
    uv run project.py add-scene --project ./my_project/ --name "Intro" --type text-to-video --prompt "..." --duration 5

    # Update project metadata
    uv run project.py update --project ./my_project/ --key vision --value "..."

    # List all scenes
    uv run project.py list-scenes --project ./my_project/

    # List all assets
    uv run project.py list-assets --project ./my_project/

    # Add a reference
    uv run project.py add-reference --project ./my_project/ --type url --content "https://..." --summary "..."

    # Export project as JSON
    uv run project.py export --project ./my_project/ --format json

    # Generate production document
    uv run project.py generate-doc --project ./my_project/ --output production_doc.md
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vision TEXT,
    style TEXT,
    status TEXT DEFAULT 'draft',
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    sequence INTEGER DEFAULT 0,
    name TEXT,
    type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    duration INTEGER DEFAULT 5,
    status TEXT DEFAULT 'pending',
    task_id TEXT,
    output_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_id TEXT,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    local_path TEXT,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    layer INTEGER DEFAULT 0,
    start_time REAL DEFAULT 0,
    duration REAL,
    volume REAL DEFAULT 1.0,
    opacity REAL DEFAULT 1.0,
    position_x TEXT DEFAULT 'center',
    position_y TEXT DEFAULT 'center',
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_references (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT,
    title TEXT,
    content TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

# File extension to asset type mapping
ASSET_TYPE_MAP = {
    # Audio
    ".wav": "audio",
    ".mp3": "audio",
    ".aac": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    # Image
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
    # Video
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".avi": "video",
    ".mkv": "video",
    # Subtitle
    ".srt": "subtitle",
    ".vtt": "subtitle",
    ".ass": "subtitle",
}


def get_db_path(project_path: str) -> str:
    """Get the database path for a project."""
    return os.path.join(project_path, "project.db")


def init_db(db_path: str):
    """Initialize the database schema."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def migrate_db(db_path: str):
    """Run database migrations to ensure all tables exist."""
    conn = sqlite3.connect(db_path)

    # Check if tracks table exists
    result = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'"
    ).fetchone()

    if not result:
        # Create tracks table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                layer INTEGER DEFAULT 0,
                start_time REAL DEFAULT 0,
                duration REAL,
                volume REAL DEFAULT 1.0,
                opacity REAL DEFAULT 1.0,
                position_x TEXT DEFAULT 'center',
                position_y TEXT DEFAULT 'center',
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        print("[MIGRATION] Created tracks table")

    conn.close()


def init_project(name: str, output: str, vision: str = None, style: str = None):
    """Initialize a new project."""
    project_path = Path(output)
    project_path.mkdir(parents=True, exist_ok=True)

    db_path = get_db_path(output)
    init_db(db_path)

    project_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO projects (id, name, vision, style, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, name, vision, style, now, now),
    )
    conn.commit()
    conn.close()

    print(f"Project initialized: {name}")
    print(f"  ID: {project_id}")
    print(f"  Path: {output}")
    print(f"  Database: {db_path}")

    # Create assets directory
    assets_dir = project_path / "assets"
    assets_dir.mkdir(exist_ok=True)
    print(f"  Assets: {assets_dir}")

    return project_id


def get_project(db_path: str) -> dict:
    """Get project info."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM projects LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def show_status(project_path: str):
    """Show project status."""
    db_path = get_db_path(project_path)
    if not os.path.exists(db_path):
        print(f"Error: No project database found at {db_path}")
        sys.exit(1)

    project = get_project(db_path)
    if not project:
        print("Error: No project found in database")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    scenes_count = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
    assets_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    refs_count = conn.execute("SELECT COUNT(*) FROM project_references").fetchone()[0]
    conn.close()

    print(f"Project: {project['name']}")
    print(f"  ID: {project['id']}")
    print(f"  Status: {project['status']}")
    print(f"  Vision: {project['vision'] or 'Not set'}")
    print(f"  Style: {project['style'] or 'Not set'}")
    print(f"  Created: {project['created_at']}")
    print(f"  Scenes: {scenes_count}")
    print(f"  Assets: {assets_count}")
    print(f"  References: {refs_count}")


def add_scene(
    project_path: str,
    name: str,
    type: str,
    prompt: str,
    duration: int = 5,
    sequence: int = None,
):
    """Add a scene to the project."""
    db_path = get_db_path(project_path)
    project = get_project(db_path)
    if not project:
        print("Error: No project found")
        sys.exit(1)

    scene_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    if sequence is None:
        max_seq = conn.execute("SELECT MAX(sequence) FROM scenes").fetchone()[0]
        sequence = (max_seq or 0) + 1

    conn.execute(
        "INSERT INTO scenes (id, project_id, sequence, name, type, prompt, duration, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (scene_id, project["id"], sequence, name, type, prompt, duration, now),
    )
    conn.commit()
    conn.close()

    print(f"Scene added: {name}")
    print(f"  ID: {scene_id}")
    print(f"  Type: {type}")
    print(f"  Duration: {duration}s")
    print(f"  Sequence: {sequence}")

    return scene_id


def list_scenes(project_path: str):
    """List all scenes in the project."""
    db_path = get_db_path(project_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM scenes ORDER BY sequence").fetchall()
    conn.close()

    if not rows:
        print("No scenes found")
        return

    print(f"Scenes ({len(rows)}):")
    for row in rows:
        print(f"  [{row['sequence']}] {row['name'] or 'Untitled'}")
        print(f"      ID: {row['id']}, Type: {row['type']}, Duration: {row['duration']}s")
        print(f"      Status: {row['status']}")
        if row['output_path']:
            print(f"      Output: {row['output_path']}")


def update_project(project_path: str, key: str, value: str):
    """Update project metadata."""
    db_path = get_db_path(project_path)
    valid_keys = ["name", "vision", "style", "status"]
    if key not in valid_keys:
        print(f"Error: Invalid key '{key}'. Valid keys: {', '.join(valid_keys)}")
        sys.exit(1)

    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(f"UPDATE projects SET {key} = ?, updated_at = ?", (value, now))
    conn.commit()
    conn.close()

    print(f"Updated {key} = {value}")


def add_asset(
    project_path: str,
    type: str,
    source: str,
    url: str = None,
    local_path: str = None,
    scene_id: str = None,
    metadata: dict = None,
):
    """Add an asset to the project."""
    db_path = get_db_path(project_path)
    project = get_project(db_path)

    asset_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO assets (id, project_id, scene_id, type, source, url, local_path, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            asset_id,
            project["id"],
            scene_id,
            type,
            source,
            url,
            local_path,
            json.dumps(metadata) if metadata else None,
            now,
        ),
    )
    conn.commit()
    conn.close()

    print(f"Asset added: {asset_id}")
    return asset_id


def list_assets(project_path: str):
    """List all assets in the project."""
    db_path = get_db_path(project_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM assets ORDER BY created_at").fetchall()
    conn.close()

    if not rows:
        print("No assets found")
        return

    print(f"Assets ({len(rows)}):")
    for row in rows:
        print(f"  [{row['type']}] {row['id']}")
        print(f"      Source: {row['source']}")
        if row['local_path']:
            print(f"      Path: {row['local_path']}")
        if row['url']:
            print(f"      URL: {row['url']}")


def add_reference(project_path: str, type: str, content: str, title: str = None, summary: str = None):
    """Add a reference to the project."""
    db_path = get_db_path(project_path)
    project = get_project(db_path)

    ref_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO project_references (id, project_id, type, title, content, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ref_id, project["id"], type, title, content, summary, now),
    )
    conn.commit()
    conn.close()

    print(f"Reference added: {ref_id}")
    return ref_id


def export_project(project_path: str, format: str = "json"):
    """Export project data."""
    db_path = get_db_path(project_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    project = get_project(db_path)
    scenes = [dict(row) for row in conn.execute("SELECT * FROM scenes ORDER BY sequence").fetchall()]
    assets = [dict(row) for row in conn.execute("SELECT * FROM assets").fetchall()]
    references = [dict(row) for row in conn.execute("SELECT * FROM project_references").fetchall()]

    conn.close()

    data = {
        "project": project,
        "scenes": scenes,
        "assets": assets,
        "references": references,
    }

    if format == "json":
        output = json.dumps(data, indent=2, default=str)
        print(output)
    else:
        print(f"Unsupported format: {format}")

    return data


def get_asset_type_from_extension(file_path: str) -> str:
    """Determine asset type from file extension."""
    ext = Path(file_path).suffix.lower()
    return ASSET_TYPE_MAP.get(ext, "unknown")


def scan_assets(project_path: str) -> list[dict]:
    """Scan assets directory for files not registered in database.

    Returns list of unregistered assets with their detected types and metadata.
    """
    db_path = get_db_path(project_path)
    assets_dir = Path(project_path) / "assets"

    if not assets_dir.exists():
        print(f"No assets directory found at {assets_dir}")
        return []

    # Get registered assets
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    registered_paths = set()
    for row in conn.execute("SELECT local_path FROM assets WHERE local_path IS NOT NULL"):
        path = row["local_path"]
        # Normalize path (remove leading assets/ if present)
        if path.startswith("assets/"):
            path = path[7:]  # Remove "assets/"
        registered_paths.add(path)
    conn.close()

    # Scan directory
    unregistered = []
    for file_path in assets_dir.iterdir():
        if file_path.is_file():
            # Get relative path from assets directory
            relative_path = file_path.name
            full_relative = f"assets/{file_path.name}"

            if relative_path not in registered_paths and full_relative not in registered_paths:
                asset_type = get_asset_type_from_extension(file_path)
                file_size = file_path.stat().st_size

                unregistered.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "relative_path": f"assets/{file_path.name}",
                    "type": asset_type,
                    "size": file_size,
                    "size_human": format_file_size(file_size),
                })

    return unregistered


def format_file_size(size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_audio_duration(file_path: str) -> float | None:
    """Get audio duration using ffprobe."""
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def register_asset(
    project_path: str,
    file_path: str,
    asset_type: str = None,
    use_case: str = None,
    create_track: bool = False,
):
    """Register an asset in the database.

    Args:
        project_path: Path to the project directory
        file_path: Path to the asset file (absolute or relative to project)
        asset_type: Type of asset (auto-detected if not specified)
        use_case: How the asset will be used (soundtrack, voiceover, sfx, etc.)
        create_track: If True, create a track for this asset
    """
    db_path = get_db_path(project_path)
    project = get_project(db_path)

    # Resolve file path
    file_path_obj = Path(file_path)
    if not file_path_obj.is_absolute():
        # Try relative to project first
        project_file = Path(project_path) / file_path
        if project_file.exists():
            file_path_obj = project_file
        else:
            print(f"Error: File not found: {file_path}")
            sys.exit(1)

    if not file_path_obj.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Auto-detect type if not specified
    if not asset_type:
        asset_type = get_asset_type_from_extension(file_path_obj)

    # Get file metadata
    metadata = {
        "use_case": use_case,
        "size": file_path_obj.stat().st_size,
    }

    # Get duration for audio/video
    if asset_type in ["audio", "video"]:
        duration = get_audio_duration(str(file_path_obj))
        if duration:
            metadata["duration"] = duration
            print(f"Detected duration: {duration:.2f}s")

    # Determine relative path for storage
    try:
        relative_path = file_path_obj.relative_to(Path(project_path))
        relative_path_str = str(relative_path)
    except ValueError:
        relative_path_str = str(file_path_obj)

    # Create asset ID
    asset_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    # Insert asset
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO assets (id, project_id, type, source, local_path, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (asset_id, project["id"], asset_type, "uploaded", relative_path_str, json.dumps(metadata), now),
    )
    conn.commit()
    conn.close()

    print(f"Asset registered: {asset_id}")
    print(f"  Type: {asset_type}")
    print(f"  Path: {relative_path_str}")
    if use_case:
        print(f"  Use case: {use_case}")

    # Create track if requested
    if create_track:
        track_name = file_path_obj.stem
        # Add file path to metadata based on asset type
        track_metadata = metadata.copy()
        if asset_type == "audio":
            track_metadata["audio_path"] = relative_path_str
        elif asset_type == "image":
            track_metadata["image_path"] = relative_path_str
        elif asset_type == "video":
            track_metadata["video_path"] = relative_path_str
        elif asset_type == "subtitle":
            track_metadata["srt_path"] = relative_path_str

        add_track(
            project_path=project_path,
            name=track_name,
            track_type=asset_type,
            asset_id=asset_id,
            metadata=track_metadata,
        )

    return asset_id


def add_track(
    project_path: str,
    name: str,
    track_type: str,
    asset_id: str = None,
    layer: int = None,
    start_time: float = 0,
    duration: float = None,
    volume: float = 1.0,
    metadata: dict = None,
):
    """Add a track (layer) to the project.

    Args:
        project_path: Path to the project directory
        name: Track name
        track_type: Type of track (video, audio, image, text, subtitle)
        asset_id: Optional linked asset ID
        layer: Layer order (0 = base, higher = on top)
        start_time: When the track starts in the video
        duration: Track duration (None = project duration)
        volume: Volume for audio tracks (0-1)
        metadata: Additional metadata
    """
    db_path = get_db_path(project_path)

    # Ensure tracks table exists (migration)
    migrate_db(db_path)

    project = get_project(db_path)

    track_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    # Determine layer if not specified
    if layer is None:
        conn = sqlite3.connect(db_path)
        max_layer = conn.execute("SELECT MAX(layer) FROM tracks WHERE project_id = ?", (project["id"],)).fetchone()[0]
        layer = (max_layer or -1) + 1
        conn.close()

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO tracks
           (id, project_id, name, type, layer, start_time, duration, volume, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (track_id, project["id"], name, track_type, layer, start_time, duration, volume, json.dumps(metadata) if metadata else None, now),
    )
    conn.commit()
    conn.close()

    print(f"Track added: {name}")
    print(f"  ID: {track_id}")
    print(f"  Type: {track_type}")
    print(f"  Layer: {layer}")
    print(f"  Start: {start_time}s")
    if duration:
        print(f"  Duration: {duration}s")
    if track_type == "audio":
        print(f"  Volume: {volume}")

    return track_id


def list_tracks(project_path: str):
    """List all tracks in the project."""
    db_path = get_db_path(project_path)

    # Ensure tracks table exists (migration)
    migrate_db(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tracks ORDER BY layer").fetchall()
    conn.close()

    if not rows:
        print("No tracks found")
        return

    print(f"Tracks ({len(rows)}):")
    for row in rows:
        print(f"  [L{row['layer']}] {row['name']} ({row['type']})")
        print(f"      ID: {row['id']}, Start: {row['start_time']}s")
        if row['duration']:
            print(f"      Duration: {row['duration']}s")
        if row['type'] == 'audio':
            print(f"      Volume: {row['volume']}")


def remove_track(project_path: str, track_id: str):
    """Remove a track from the project."""
    db_path = get_db_path(project_path)

    # Ensure tracks table exists (migration)
    migrate_db(db_path)

    conn = sqlite3.connect(db_path)

    # Check if track exists
    row = conn.execute("SELECT name FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if not row:
        print(f"Error: Track not found: {track_id}")
        conn.close()
        sys.exit(1)

    track_name = row[0]
    conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    conn.commit()
    conn.close()

    print(f"Track removed: {track_name} ({track_id})")


def main():
    parser = argparse.ArgumentParser(description="Manage media production projects")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("name", help="Project name")
    init_parser.add_argument("--output", "-o", default="./project/", help="Output directory")
    init_parser.add_argument("--vision", help="Project vision statement")
    init_parser.add_argument("--style", help="Visual style description")

    # status command
    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("--project", "-p", required=True, help="Project directory")

    # add-scene command
    scene_parser = subparsers.add_parser("add-scene", help="Add a scene")
    scene_parser.add_argument("--project", "-p", required=True, help="Project directory")
    scene_parser.add_argument("--name", help="Scene name")
    scene_parser.add_argument("--type", required=True, choices=["text-to-video", "image-to-video", "frame-transition"])
    scene_parser.add_argument("--prompt", required=True, help="Scene prompt")
    scene_parser.add_argument("--duration", type=int, default=5, help="Duration in seconds")
    scene_parser.add_argument("--sequence", type=int, help="Sequence order")

    # list-scenes command
    list_scenes_parser = subparsers.add_parser("list-scenes", help="List all scenes")
    list_scenes_parser.add_argument("--project", "-p", required=True, help="Project directory")

    # update command
    update_parser = subparsers.add_parser("update", help="Update project metadata")
    update_parser.add_argument("--project", "-p", required=True, help="Project directory")
    update_parser.add_argument("--key", required=True, choices=["name", "vision", "style", "status"])
    update_parser.add_argument("--value", required=True)

    # add-asset command
    asset_parser = subparsers.add_parser("add-asset", help="Add an asset")
    asset_parser.add_argument("--project", "-p", required=True, help="Project directory")
    asset_parser.add_argument("--type", required=True, choices=["image", "video", "reference"])
    asset_parser.add_argument("--source", required=True, choices=["generated", "uploaded", "external_url"])
    asset_parser.add_argument("--url", help="External URL")
    asset_parser.add_argument("--local-path", help="Local file path")
    asset_parser.add_argument("--scene-id", help="Link to scene")

    # list-assets command
    list_assets_parser = subparsers.add_parser("list-assets", help="List all assets")
    list_assets_parser.add_argument("--project", "-p", required=True, help="Project directory")

    # scan-assets command
    scan_parser = subparsers.add_parser("scan-assets", help="Scan for unregistered assets")
    scan_parser.add_argument("--project", "-p", required=True, help="Project directory")

    # register-asset command
    register_parser = subparsers.add_parser("register-asset", help="Register an asset file")
    register_parser.add_argument("--project", "-p", required=True, help="Project directory")
    register_parser.add_argument("--file", "-f", required=True, help="File path to register")
    register_parser.add_argument("--type", choices=["audio", "image", "video", "subtitle"], help="Asset type (auto-detected if not specified)")
    register_parser.add_argument("--use-case", choices=["soundtrack", "voiceover", "sfx", "overlay", "background"], help="How the asset will be used")
    register_parser.add_argument("--create-track", action="store_true", help="Create a track for this asset")

    # add-track command
    track_parser = subparsers.add_parser("add-track", help="Add a track (layer)")
    track_parser.add_argument("--project", "-p", required=True, help="Project directory")
    track_parser.add_argument("--name", required=True, help="Track name")
    track_parser.add_argument("--type", required=True, choices=["video", "audio", "image", "text", "subtitle"])
    track_parser.add_argument("--layer", type=int, help="Layer order (0 = base)")
    track_parser.add_argument("--start-time", type=float, default=0, help="Start time in seconds")
    track_parser.add_argument("--duration", type=float, help="Duration in seconds")
    track_parser.add_argument("--volume", type=float, default=1.0, help="Volume for audio tracks")

    # list-tracks command
    list_tracks_parser = subparsers.add_parser("list-tracks", help="List all tracks")
    list_tracks_parser.add_argument("--project", "-p", required=True, help="Project directory")

    # remove-track command
    remove_track_parser = subparsers.add_parser("remove-track", help="Remove a track")
    remove_track_parser.add_argument("--project", "-p", required=True, help="Project directory")
    remove_track_parser.add_argument("--track-id", required=True, help="Track ID to remove")

    # add-reference command
    ref_parser = subparsers.add_parser("add-reference", help="Add a reference")
    ref_parser.add_argument("--project", "-p", required=True, help="Project directory")
    ref_parser.add_argument("--type", default="url", choices=["url", "article", "paper", "image"])
    ref_parser.add_argument("--content", required=True, help="URL or content")
    ref_parser.add_argument("--title", help="Reference title")
    ref_parser.add_argument("--summary", help="Summary of the reference")

    # export command
    export_parser = subparsers.add_parser("export", help="Export project data")
    export_parser.add_argument("--project", "-p", required=True, help="Project directory")
    export_parser.add_argument("--format", choices=["json"], default="json")

    args = parser.parse_args()

    if args.command == "init":
        init_project(args.name, args.output, args.vision, args.style)
    elif args.command == "status":
        show_status(args.project)
    elif args.command == "add-scene":
        add_scene(args.project, args.name, args.type, args.prompt, args.duration, args.sequence)
    elif args.command == "list-scenes":
        list_scenes(args.project)
    elif args.command == "update":
        update_project(args.project, args.key, args.value)
    elif args.command == "add-asset":
        add_asset(args.project, args.type, args.source, args.url, args.local_path, args.scene_id)
    elif args.command == "list-assets":
        list_assets(args.project)
    elif args.command == "scan-assets":
        unregistered = scan_assets(args.project)
        if unregistered:
            print(f"Found {len(unregistered)} unregistered assets:\n")
            for asset in unregistered:
                print(f"  [{asset['type']}] {asset['filename']}")
                print(f"      Path: {asset['relative_path']}")
                print(f"      Size: {asset['size_human']}")
                if 'duration' in asset.get('metadata', {}):
                    print(f"      Duration: {asset['metadata']['duration']:.2f}s")
        else:
            print("No unregistered assets found")
    elif args.command == "register-asset":
        register_asset(args.project, args.file, args.type, args.use_case, args.create_track)
    elif args.command == "add-track":
        add_track(args.project, args.name, args.type, layer=args.layer, start_time=args.start_time, duration=args.duration, volume=args.volume)
    elif args.command == "list-tracks":
        list_tracks(args.project)
    elif args.command == "remove-track":
        remove_track(args.project, args.track_id)
    elif args.command == "add-reference":
        add_reference(args.project, args.type, args.content, args.title, args.summary)
    elif args.command == "export":
        export_project(args.project, args.format)


if __name__ == "__main__":
    main()
