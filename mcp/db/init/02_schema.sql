CREATE TABLE authors (
    author_id    SERIAL PRIMARY KEY,
    display_name TEXT NOT NULL,
    is_committer BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_authors_display_name ON authors USING GIN (display_name gin_trgm_ops);

CREATE TABLE author_emails (
    email     TEXT PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE
);

CREATE INDEX idx_author_emails_author ON author_emails (author_id);

CREATE TABLE threads (
    thread_id   TEXT PRIMARY KEY,
    subject     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'discussion',
    list_names  TEXT[] NOT NULL DEFAULT '{}',
    started_at  TIMESTAMPTZ,
    ended_at    TIMESTAMPTZ
);

CREATE INDEX idx_threads_status ON threads (status);
CREATE INDEX idx_threads_started_at ON threads (started_at);
CREATE INDEX idx_threads_ended_at ON threads (ended_at);
CREATE INDEX idx_threads_list_names ON threads USING GIN (list_names);

CREATE TABLE messages (
    message_id  TEXT PRIMARY KEY,
    list_name   TEXT NOT NULL DEFAULT 'pgsql-hackers',
    thread_id   TEXT REFERENCES threads(thread_id),
    parent_id   TEXT,
    sender      TEXT NOT NULL,
    author_id   INTEGER REFERENCES authors(author_id),
    sent_at     TIMESTAMPTZ,
    subject     TEXT,
    body        TEXT,
    body_raw    TEXT,
    body_tsv    TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(body, ''))) STORED
);

-- tsvector full-text search (natural language queries)
CREATE INDEX idx_messages_tsv ON messages USING GIN (body_tsv);

-- pg_trgm trigram search (identifiers, partial string matching)
CREATE INDEX idx_messages_body_trgm ON messages USING GIN (body gin_trgm_ops);

CREATE INDEX idx_messages_thread ON messages (thread_id);
CREATE INDEX idx_messages_sent_at ON messages (sent_at);
CREATE INDEX idx_messages_sender ON messages (sender);
CREATE INDEX idx_messages_author ON messages (author_id);
CREATE INDEX idx_messages_parent ON messages (parent_id);
CREATE INDEX idx_messages_list_name ON messages (list_name);

CREATE TABLE patches (
    patch_id        SERIAL PRIMARY KEY,
    message_id      TEXT REFERENCES messages(message_id),
    filename        TEXT,
    content_type    TEXT,
    files_changed   TEXT[],
    raw_diff        TEXT
);

CREATE INDEX idx_patches_message ON patches (message_id);
CREATE INDEX idx_patches_files ON patches USING GIN (files_changed);

CREATE TABLE ingestion_log (
    mbox_file       TEXT PRIMARY KEY,
    message_count   INTEGER NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
