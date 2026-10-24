"""Eligibility, transparent relevance scoring, and deterministic list diversity."""
import math
from collections import Counter, defaultdict
from datetime import datetime

VERSION = 'topics-activity-v1'
MAX_USER_ID = 2**63 - 1  # SQLite INTEGER range.


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def recommendations(db, user_id, limit=5):
    if not 1 <= limit <= 20:
        raise ValueError('limit must be between 1 and 20')
    if not 1 <= user_id <= MAX_USER_ID:
        raise ValueError('user_id must be between 1 and 9223372036854775807')
    if not db.execute('SELECT 1 FROM users WHERE id = ?', (user_id,)).fetchone():
        raise LookupError('User not found')
    snapshot = db.execute("SELECT value FROM metadata WHERE key = 'snapshot_at'").fetchone()[0]
    now = parse_time(snapshot)
    labels = {r['slug']: r['label'] for r in db.execute('SELECT slug, label FROM topics')}
    explicit = {r[0] for r in db.execute('SELECT topic_slug FROM user_interests WHERE user_id = ?', (user_id,))}
    inferred = set()
    if not explicit:
        inferred = {r[0] for r in db.execute('SELECT DISTINCT c.topic FROM memberships m JOIN circles c ON c.id=m.circle_id WHERE m.user_id=? AND c.topic IS NOT NULL', (user_id,))}
    interests = explicit or inferred
    strength = 1.0 if explicit else 0.35
    tags = defaultdict(set)
    for r in db.execute('SELECT circle_id, tag FROM circle_tags'):
        tags[r[0]].add(r[1])
    candidates = []
    # Use the supplied capacity aggregate without recounting memberships per Circle.
    rows = db.execute('''SELECT c.* FROM circles c WHERE access='public'
        AND (max_members IS NULL OR member_count < max_members)
        AND feed_posts_30d + chat_messages_30d > 0
        AND julianday(last_activity_at) BETWEEN julianday(?, '-60 days') AND julianday(?)
        AND NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id=? AND m.circle_id=c.id)''', (snapshot, snapshot, user_id))
    for row in rows:
        c = dict(row)
        age = (now - parse_time(c['last_activity_at'])).total_seconds() / 86400
        primary = c['topic'] in interests
        matched = interests & (tags[c['id']] | ({c['topic']} if c['topic'] else set()))
        relevance = strength * ((65 if primary else 39 if matched else 0) + min(5, 5 * max(0, len(matched) - 1)))
        # Logs bound the benefit of raw volume; a large group cannot dominate on volume alone.
        activity = 25 * (0.4 * min(1, math.log1p(c['feed_posts_30d']) / math.log(31))
                         + 0.4 * min(1, math.log1p(c['chat_messages_30d']) / math.log(301))
                         + 0.2 * math.exp(-age / 30))
        score = relevance + activity + (5 if c['join_policy'] == 'open' else 0)
        reasons = []
        if matched:
            topic = c['topic'] if primary else sorted(matched)[0]
            label = labels.get(topic, topic).lower()
            reasons.append(f'Matches your interest in {label}.' if explicit else f'Explores {label}, a topic in a Circle you belong to.')
        else:
            reasons.append('An active community to explore as you build your Circle connections.')
        if c['feed_posts_30d']:
            reasons.append(f"{c['feed_posts_30d']} posts in the 30 days before this snapshot.")
        else:
            reasons.append('Members have been active in the group chat during this snapshot’s last 30 days.')
        reasons.append('Open to join.' if c['join_policy'] == 'open' else 'Accepting requests to join.')
        c.update(base_score=score, explanation=' '.join(reasons))
        candidates.append(c)
    chosen = []
    counts = Counter()
    while candidates and len(chosen) < limit:
        # Hard cap prevents three near-identical primary-topic Circles; a soft
        # penalty spreads topics earlier while retaining strong second matches.
        eligible = [c for c in candidates if not c['topic'] or counts[c['topic']] < 2]
        if not eligible:
            break
        def adjusted(c):
            return c['base_score'] - (15 * counts[c['topic']] if c['topic'] else 0)
        best = max(eligible, key=lambda c: (adjusted(c), -c['id']))
        chosen.append({
            'rank': len(chosen) + 1,
            'circle': {k: best[k] for k in ('id', 'name', 'slug', 'description', 'topic', 'format', 'join_policy', 'member_count', 'max_members')},
            'score': round(adjusted(best), 4),
            'explanation': best['explanation'],
        })
        counts[best['topic']] += 1
        candidates.remove(best)
    return {'user_id': user_id, 'snapshot_at': snapshot, 'algorithm_version': VERSION,
            'strategy': 'stated_interests' if explicit else 'membership_topics' if inferred else 'explore',
            'recommendations': chosen}
