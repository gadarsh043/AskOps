-- Add webhook_url to workspaces so n8n can build approval email links
-- without depending on a runtime env-var that changes on every tunnel restart.
ALTER TABLE workspaces
  ADD COLUMN IF NOT EXISTS webhook_url text NOT NULL DEFAULT 'http://localhost:5678';
