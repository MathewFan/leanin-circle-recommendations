import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / 'var' / 'circles.sqlite3'
SNAPSHOT_AT = '2026-09-21T00:00:00Z'  # ANCHOR in the supplied generator.


def connect(path=DEFAULT_DB):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA query_only = ON')
    return connection


def seed(path=DEFAULT_DB):
    """Create once; refuse to silently overwrite a preexisting database."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents accidental reset of an existing submission DB.
    with path.open('xb'):
        pass
    connection = sqlite3.connect(path)
    try:
        connection.executescript((ROOT / 'schema.sql').read_text())
        with connection:
            connection.execute('INSERT INTO metadata VALUES (?, ?)', ('snapshot_at', SNAPSHOT_AT))
            for table in ('topics', 'users', 'circles', 'memberships', 'activity'):
                for original in json.loads((ROOT / 'data' / f'{table}.json').read_text()):
                    row = dict(original)
                    interests = row.pop('topic_interests', [])
                    tags = row.pop('tags', [])
                    columns = ','.join(row)
                    placeholders = ','.join('?' for _ in row)
                    connection.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(row.values()))
                    if table == 'users':
                        connection.executemany('INSERT INTO user_interests VALUES (?, ?)', [(row['id'], t) for t in set(interests)])
                    if table == 'circles':
                        connection.executemany('INSERT INTO circle_tags VALUES (?, ?)', [(row['id'], t) for t in set(tags)])
            if connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Seed contains invalid relationships')
    except Exception:
        connection.close()
        path.unlink()
        raise
    finally:
        connection.close()


if __name__ == '__main__':
    seed()
    print(f'Created {DEFAULT_DB}')
