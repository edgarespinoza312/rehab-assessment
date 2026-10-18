import os


# Application tests must never mutate the file-backed development database.
os.environ.setdefault("REVALIV_DATABASE_URI", "sqlite://")
