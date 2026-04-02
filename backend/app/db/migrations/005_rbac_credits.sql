-- 005_rbac_credits.sql
-- Add RBAC access_role and credits columns for admin dashboard

-- Users: add access_role (separate from LLM role) and credits
ALTER TABLE users ADD COLUMN IF NOT EXISTS access_role TEXT NOT NULL DEFAULT 'employee';
ALTER TABLE users ADD COLUMN IF NOT EXISTS credits INTEGER NOT NULL DEFAULT 0;

-- Auth sessions: cache access_role for fast auth checks
ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS access_role TEXT NOT NULL DEFAULT 'employee';
