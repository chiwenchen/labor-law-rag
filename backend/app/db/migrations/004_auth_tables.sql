-- 004_auth_tables.sql
-- Replace in-memory OTP, pending registration, and session stores with DB tables

CREATE TABLE IF NOT EXISTS otp_codes (
    email       TEXT PRIMARY KEY,
    otp         TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_registrations (
    token       TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token       TEXT PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('hr', 'employee')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
