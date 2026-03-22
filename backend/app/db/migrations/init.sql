CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS law_articles (
    id SERIAL PRIMARY KEY,
    article_number VARCHAR(20) UNIQUE NOT NULL,
    title VARCHAR(200),
    content TEXT NOT NULL,
    embedding vector(1024),
    is_active BOOLEAN DEFAULT true,
    last_updated TIMESTAMP WITH TIME ZONE,
    version VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS law_articles_embedding_idx
    ON law_articles USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT,
    cited_articles JSONB,
    max_similarity_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE IF NOT EXISTS law_update_logs (
    id SERIAL PRIMARY KEY,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    articles_changed INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    error_message TEXT
);
