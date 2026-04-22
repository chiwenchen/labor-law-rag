-- 005_user_access_role_credits.sql
-- Add columns the ORM expects but that were never in a migration.
-- (users.access_role, users.credits, auth_sessions.access_role)

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS access_role VARCHAR(20) NOT NULL DEFAULT 'employee',
  ADD COLUMN IF NOT EXISTS credits     INTEGER     NOT NULL DEFAULT 0;

ALTER TABLE auth_sessions
  ADD COLUMN IF NOT EXISTS access_role VARCHAR(20) NOT NULL DEFAULT 'employee';
