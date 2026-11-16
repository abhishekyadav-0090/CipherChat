-- CipherChat database schema (SQLite)
-- Loaded automatically by database.database.Database.init_schema().

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    last_seen_at  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    token_hash  TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL,
    ip_address  TEXT,
    revoked_at  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS groups (
    group_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    owner_id   INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id  INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    joined_at TEXT    NOT NULL,
    PRIMARY KEY (group_id, user_id),
    FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(user_id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id   INTEGER NOT NULL,
    receiver_id INTEGER,
    group_id    INTEGER,
    body        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'stored',  -- stored | delivered | read
    timestamp   TEXT    NOT NULL,
    delivered_at TEXT,
    FOREIGN KEY (sender_id)   REFERENCES users(user_id)  ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(user_id)  ON DELETE SET NULL,
    FOREIGN KEY (group_id)    REFERENCES groups(group_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS connection_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    event_type  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    ip_address  TEXT,
    detail      TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_pair
    ON messages (sender_id, receiver_id, message_id);
CREATE INDEX IF NOT EXISTS idx_messages_receiver_status
    ON messages (receiver_id, status);
CREATE INDEX IF NOT EXISTS idx_messages_group
    ON messages (group_id, message_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token
    ON sessions (token_hash);
CREATE INDEX IF NOT EXISTS idx_logs_time
    ON connection_logs (timestamp);
