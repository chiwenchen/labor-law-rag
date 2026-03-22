-- Add law_id and law_name to law_articles
ALTER TABLE law_articles
  ADD COLUMN IF NOT EXISTS law_id   VARCHAR(20)  NOT NULL DEFAULT 'N0030001',
  ADD COLUMN IF NOT EXISTS law_name VARCHAR(100) NOT NULL DEFAULT '勞動基準法';

-- Replace single-column unique constraint with composite (law_id, article_number)
ALTER TABLE law_articles
  DROP CONSTRAINT IF EXISTS law_articles_article_number_key;
ALTER TABLE law_articles
  ADD CONSTRAINT law_articles_law_id_article_number_key
    UNIQUE (law_id, article_number);

-- Add law_id to law_update_logs
ALTER TABLE law_update_logs
  ADD COLUMN IF NOT EXISTS law_id VARCHAR(20) NOT NULL DEFAULT 'N0030001';

-- Create supported_laws summary table
CREATE TABLE IF NOT EXISTS supported_laws (
  law_id        VARCHAR(20)  PRIMARY KEY,
  law_name      VARCHAR(100) NOT NULL,
  article_count INTEGER      NOT NULL DEFAULT 0,
  last_updated  TIMESTAMP WITH TIME ZONE,
  last_status   VARCHAR(20)  NOT NULL DEFAULT 'never_run'
);
