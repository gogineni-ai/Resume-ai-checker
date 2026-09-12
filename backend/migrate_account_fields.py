from sqlalchemy import text
from app.db import engine

statements = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE",
    """
    CREATE TABLE IF NOT EXISTS verification_codes (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        channel VARCHAR(20) NOT NULL,
        destination VARCHAR(255) NOT NULL,
        code_hash VARCHAR(255) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        used_at TIMESTAMPTZ NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_verification_codes_user_id ON verification_codes(user_id)",
]

with engine.begin() as conn:
    for statement in statements:
        conn.execute(text(statement))

    duplicates = conn.execute(text("""
        SELECT btrim(phone) AS phone, COUNT(*)
        FROM users
        WHERE phone IS NOT NULL AND btrim(phone) <> ''
        GROUP BY btrim(phone)
        HAVING COUNT(*) > 1
    """)).fetchall()

    if duplicates:
        print("Duplicate phone numbers found. Unique index was NOT created:")
        for row in duplicates:
            print(row)
    else:
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone
            ON users(phone)
            WHERE phone IS NOT NULL
        """))
        print("Unique phone index created.")

print("Account migration complete.")
