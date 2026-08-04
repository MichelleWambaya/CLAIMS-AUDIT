-- Run this in Supabase's SQL Editor to create your first login.
-- Enable pgcrypto first if it isn't already (Database -> Extensions -> pgcrypto),
-- since crypt()/gen_salt() below depend on it.

-- If you already ran the original db/schema.sql, it was missing this
-- column (a real bug, now fixed in schema.sql) — add it before inserting:
ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password TEXT;
ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL;
-- If that second line errors because existing rows have no value, either
-- delete any placeholder rows first or drop the NOT NULL constraint for now.

INSERT INTO users (email, display_name, role, hashed_password)
VALUES (
    'you@example.com',           -- change to your real email
    'Admin',                     -- change to your real name
    'admin',
    crypt('ChangeThisPassword123', gen_salt('bf'))  -- change the password
);
