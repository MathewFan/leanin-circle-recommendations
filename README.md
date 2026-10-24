# Circles worth joining

A small, explainable recommendation API for the supplied synthetic Lean In dataset. Uses Python's standard library and SQLite; no packages, services, API keys, or model downloads are needed.

## Run locally

Requires Python 3.9+ with SQLite support. From this repository's root:

```sh
python3 -m app.db
python3 -m app.server
```

In another terminal:

```sh
curl 'http://127.0.0.1:8000/users/7/recommendations?limit=5'
```

The server binds to localhost. Stop with Ctrl+C. If port 8000 is busy, use `python3 -m app.server --port 8001`. Seeding creates `var/circles.sqlite3` and refuses to overwrite an existing database. To reset the demo, stop the server, delete that one file, and rerun the seed command. The original dataset and deterministic generator are included; its dictionary is in [data/README.md](data/README.md).

## API contract

`GET /users/{user_id}/recommendations?limit=5`

- `user_id`: positive integer identifying an existing member, up to SQLite’s maximum of `9223372036854775807`. Larger IDs return 400.
- `limit`: optional integer from 1 to 20; default 5. Unknown or repeated parameters return 400.
- Returns 200 with `user_id`, `snapshot_at`, `algorithm_version`, `strategy`, and `recommendations`.
- Each recommendation contains a consecutive `rank`, public Circle details, a numeric `score`, and a short member-facing `explanation`.
- Strategies: `stated_interests`, `membership_topics`, or `explore`.
- Scores are deterministic ranking utilities after diversity penalties, not probabilities or comparable measures of member suitability across users.
- An unknown user or route returns 404. Invalid query parameters return 400. Unexpected failures return a generic 500 and are logged locally.
- Results may be shorter than the requested limit, including empty, when eligibility or diversity leaves fewer candidates. Ineligible Circles are never used to fill a list.

`GET /health` returns `{"status":"ok"}` for process liveness.

Example result item for user 7:

```json
{
  "rank": 1,
  "circle": {
    "id": 6,
    "name": "Speak Up Circle",
    "slug": "speak-up-circle",
    "description": "A supportive circle for women focused on public speaking.",
    "topic": "public-speaking",
    "format": "in_person",
    "join_policy": "open",
    "member_count": 9,
    "max_members": 13
  },
  "score": 93.2546,
  "explanation": "Matches your interest in public speaking. 8 posts in the 30 days before this snapshot. Open to join."
}
```

## How ranking works

1. Exclude unlisted Circles, existing memberships, full Circles, future-dated last activity, last activity over 60 days old, and Circles with no posts or chat messages in the snapshot's last 30 days.
2. Use stated interests when available; otherwise use the primary topics of Circles the user already belongs to. With neither, recommend active, available communities to explore.
3. Relevance contributes 65 for a primary-topic match or 39 for tag-only overlap, plus 5 for a second matched interest. Membership-derived relevance receives 35% of these points. Tags are deduplicated, and a primary topic repeated as a tag gets no extra credit.
4. Activity contributes up to 25: `25 × (0.4 × min(1, ln(1+posts)/ln(31)) + 0.4 × min(1, ln(1+chat)/ln(301)) + 0.2 × exp(-days_since_activity/30))`. Open joining adds 5; request-to-join Circles remain eligible.
5. Select greedily, subtracting 15 for each previously selected Circle with the same primary topic. Allow at most two per primary topic. Null topics do not form one artificial topic group. Ties use the smaller Circle ID.

The thresholds and weights are understandable initial heuristics, not learned or empirically validated. The same ranking logic applies to every user; there are no branches for planted IDs. Diversity is based on taxonomy and will miss semantically duplicate Circles assigned different topics.

### Snapshot time and data limitations

The generator fixes `ANCHOR` at **2026-09-21 00:00 UTC**. The seed records that time as database metadata, and every response reports it. Activity aggregates describe that snapshot, so using today's clock would incorrectly age an unchanged demo. For production, refresh aggregates and their as-of time together; changing only the clock would misrepresent 30-day counts.

`member_count` is authoritative for capacity. The supplied membership rows match that aggregate; the API uses the stored count to avoid recounting memberships during recommendation requests. Join availability can change after recommendation; the actual join operation must recheck capacity atomically.

Circle meeting location and member format preferences are absent. The API returns the format but does not claim geographic suitability; meeting location needs confirmation before joining an in-person or hybrid Circle. It does not infer gender, race, parenting status, or career stage from names, biographies, or titles. Profile completeness and photos do not affect opportunity to receive recommendations. There is no network dataset.

This is a local demo: it has no authentication or authorization. Production must derive the member identity from an authenticated session and enforce visibility at every read. Never expose the demo directly to the internet.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

Twelve tests cover real HTTP responses, validation, all 100 users, eligibility, capacity boundaries, chat-only activity, deterministic ranking, membership fallback, empty pools, schema relationships, seed overwrite protection, oversized user IDs, and activity-window boundaries. The inactive fixture is also tested after making it public so its unlisted status cannot mask a broken activity filter.

Observed default results for the planted records:

| User | First five Circle IDs | Expected behavior |
| --- | --- | --- |
| 42 | 1, 11, 31, 13, 39 | Active, joinable exploration without requiring a completed profile |
| 7 | 6, 1, 5, 38, 31 | Speak Up Circle and Women Who Lead both in the top three |
| 15 | 13, 11, 10, 37, 38 | Two of the three negotiation duplicates; confidence also represented |
| 23 | 22, 19, 2, 16, 1 | Healthy promotion match first; full #20 and stale #21 excluded |

## Design and submission

- [One-page technical design](DESIGN.md)
- [Schema and index rationale](SCHEMA.md), executable [schema.sql](schema.sql)

