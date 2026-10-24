PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE topics (id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, label TEXT NOT NULL, domain TEXT NOT NULL);
CREATE TABLE users (
 id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
 has_photo INTEGER NOT NULL CHECK(has_photo IN (0,1)), bio TEXT, job_title TEXT,
 company TEXT, industry TEXT, location TEXT, joined_at TEXT NOT NULL,
 profile_completeness REAL NOT NULL CHECK(profile_completeness BETWEEN 0 AND 1)
);
CREATE TABLE user_interests (
 user_id INTEGER NOT NULL REFERENCES users(id), topic_slug TEXT NOT NULL REFERENCES topics(slug),
 PRIMARY KEY(user_id, topic_slug)
);
CREATE TABLE circles (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, description TEXT,
 topic TEXT REFERENCES topics(slug), cover_image_url TEXT,
 format TEXT NOT NULL CHECK(format IN ('in_person','virtual','hybrid')),
 access TEXT NOT NULL CHECK(access IN ('public','unlisted')),
 join_policy TEXT NOT NULL CHECK(join_policy IN ('open','request')),
 max_members INTEGER CHECK(max_members > 0), member_count INTEGER NOT NULL CHECK(member_count >= 0),
 created_at TEXT NOT NULL, last_activity_at TEXT NOT NULL,
 feed_posts_30d INTEGER NOT NULL CHECK(feed_posts_30d >= 0),
 chat_messages_30d INTEGER NOT NULL CHECK(chat_messages_30d >= 0)
);
CREATE TABLE circle_tags (
 circle_id INTEGER NOT NULL REFERENCES circles(id), tag TEXT NOT NULL,
 PRIMARY KEY(circle_id, tag)
);
CREATE TABLE memberships (
 user_id INTEGER NOT NULL REFERENCES users(id), circle_id INTEGER NOT NULL REFERENCES circles(id),
 role TEXT NOT NULL CHECK(role IN ('member','leader')), joined_at TEXT NOT NULL,
 PRIMARY KEY(user_id, circle_id)
);
CREATE INDEX memberships_circle ON memberships(circle_id, role);
CREATE TABLE activity (
 id INTEGER PRIMARY KEY, circle_id INTEGER NOT NULL, author_user_id INTEGER NOT NULL,
 body TEXT NOT NULL, reaction_count INTEGER NOT NULL CHECK(reaction_count >= 0),
 comment_count INTEGER NOT NULL CHECK(comment_count >= 0), save_count INTEGER NOT NULL CHECK(save_count >= 0),
 created_at TEXT NOT NULL,
 FOREIGN KEY(author_user_id, circle_id) REFERENCES memberships(user_id, circle_id)
);
CREATE INDEX activity_circle_time ON activity(circle_id, created_at);
CREATE INDEX circles_discovery ON circles(access, last_activity_at);
