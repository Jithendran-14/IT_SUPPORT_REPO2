"""Create the workshop destination without altering existing tables."""
import os
import sys

import oracledb


USER = "IT_SUPPORT_WORKSHOP"
TABLE = "IT_SUPPORT_EMBEDDINGS"


def main():
    for name in ("IAT_IT_USER", "IAT_IT_PASSWORD", "IAT_IT_DSN"):
        if not os.environ.get(name):
            raise RuntimeError(f"Setup incomplete: missing {name}. See README.md.")
    if os.environ["IAT_IT_USER"].upper() != USER:
        raise RuntimeError(
            "Use IT_SUPPORT_WORKSHOP. The main application's user is not allowed."
        )

    with oracledb.connect(
        user=os.environ["IAT_IT_USER"],
        password=os.environ["IAT_IT_PASSWORD"],
        dsn=os.environ["IAT_IT_DSN"],
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT USER, SYS_CONTEXT('USERENV', 'CON_NAME') FROM dual"
            )
            user, container = cursor.fetchone()
            print("Connected user:", user)
            print("Container:", container)
            if user != USER or container != "FREEPDB1":
                raise RuntimeError("Use IT_SUPPORT_WORKSHOP in FREEPDB1.")

            cursor.execute(
                "SELECT COUNT(*) FROM user_tables WHERE table_name = :name",
                name=TABLE,
            )
            if cursor.fetchone()[0]:
                print("Existing table left unchanged:", TABLE)
            else:
                cursor.execute("""
                    CREATE TABLE IT_SUPPORT_EMBEDDINGS (
                        id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        text CLOB NOT NULL,
                        preserved_original_text CLOB,
                        embedding VECTOR(1024, FLOAT32) NOT NULL,
                        metadata CLOB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT its_workshop_metadata_json
                            CHECK (metadata IS JSON)
                    )
                """)
                print("Created:", TABLE)

            cursor.execute(
                "SELECT column_name FROM user_tab_columns "
                "WHERE table_name = :name", name=TABLE
            )
            columns = {row[0] for row in cursor}
            required = {
                "ID", "TEXT", "PRESERVED_ORIGINAL_TEXT", "EMBEDDING",
                "METADATA", "CREATED_AT",
            }
            if not required.issubset(columns):
                raise RuntimeError("Existing table has unexpected columns; not modified.")
            cursor.execute("SELECT COUNT(*) FROM IT_SUPPORT_EMBEDDINGS")
            print("Stored rows:", cursor.fetchone()[0])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[SETUP ERROR] {type(error).__name__}: {error}")
        sys.exit(1)
