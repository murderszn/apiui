-- SQL to create the user_logins table in Supabase
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS user_logins (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password TEXT NOT NULL,
    login_time TIMESTAMP WITH TIME ZONE NOT NULL,
    user_agent TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_logins_email ON user_logins(email);
CREATE INDEX IF NOT EXISTS idx_user_logins_time ON user_logins(login_time);

-- Optional: Create a view for login analytics
CREATE OR REPLACE VIEW login_analytics AS
SELECT
    DATE(login_time) as login_date,
    COUNT(*) as login_count,
    COUNT(DISTINCT email) as unique_users
FROM user_logins
GROUP BY DATE(login_time)
ORDER BY login_date DESC;
