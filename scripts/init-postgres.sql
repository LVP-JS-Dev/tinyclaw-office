-- Initialize pgvector extension for MemU vector storage
-- This script runs automatically on container creation

-- Create the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension is installed
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- Create MemU tables (will be initialized by the application)
-- This is a placeholder - actual schema is created by MemU SDK
