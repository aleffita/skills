-- Media Producer Project Schema
-- SQLite database schema for managing production projects

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vision TEXT,
    style TEXT,
    status TEXT DEFAULT 'draft',  -- draft, in_production, completed, cancelled
    config JSON,  -- JSON with resolution, fps, quality settings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scenes table (shots within a project)
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    sequence INTEGER DEFAULT 0,
    name TEXT,
    type TEXT NOT NULL,  -- text-to-video, image-to-video, frame-transition
    prompt TEXT NOT NULL,
    duration INTEGER DEFAULT 5,  -- seconds
    status TEXT DEFAULT 'pending',  -- pending, generating, completed, failed
    task_id TEXT,  -- API task ID for async operations
    output_path TEXT,  -- Local path to generated video
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Assets table (images, videos, references)
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_id TEXT,  -- Optional: link to specific scene
    type TEXT NOT NULL,  -- image, video, reference
    source TEXT NOT NULL,  -- generated, uploaded, external_url
    url TEXT,  -- External URL if applicable
    local_path TEXT,  -- Local file path
    metadata JSON,  -- Additional metadata (size, format, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL
);

-- References table (articles, papers, inspiration links)
CREATE TABLE IF NOT EXISTS references (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    type TEXT,  -- url, article, paper, image
    title TEXT,
    content TEXT,  -- URL or extracted content
    summary TEXT,  -- AI-generated summary
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Generation history (for retry/resume)
CREATE TABLE IF NOT EXISTS generation_history (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    scene_id TEXT,
    model TEXT NOT NULL,  -- CogVideoX-3, CogView-4-250304, etc.
    task_id TEXT,
    status TEXT,  -- pending, processing, success, failed
    request_payload JSON,
    response JSON,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_status ON scenes(status);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
CREATE INDEX IF NOT EXISTS idx_assets_scene ON assets(scene_id);
CREATE INDEX IF NOT EXISTS idx_gen_history_task ON generation_history(task_id);
