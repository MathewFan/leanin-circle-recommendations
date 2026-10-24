# Database schema and rationale

The executable definition is [schema.sql](schema.sql). All timestamps retain the source's ISO UTC values. The application parses timestamps before recency calculations. Every application read enables foreign keys and query-only mode; seeding enables foreign keys before loading data.

| Table | Key and relationships | Purpose |
| --- | --- | --- |
| `metadata` | `key` primary key | Records the activity snapshot's as-of time |
| `topics` | Integer PK; unique `slug` | Canonical taxonomy with display labels |
| `users` | Integer PK | Preserves supplied member profile attributes |
| `user_interests` | Composite PK `(user_id, topic_slug)`; FKs to users and topics | Normalized many-to-many explicit interests |
| `circles` | Integer PK; unique `slug`; nullable `topic` FK to topic slug | Discovery, capacity, format, and activity aggregates |
| `circle_tags` | Composite PK `(circle_id, tag)`; FK to Circle | Deduplicated free-form tags, deliberately not constrained to taxonomy |
| `memberships` | Composite PK `(user_id, circle_id)`; FKs to users and Circles | One role per membership; leaders remain members |
| `activity` | Integer PK; composite FK `(author_user_id, circle_id)` to memberships | Preserves feed posts and engagement; enforces author membership |

The Circle's main topic uses the existing unique slug as a foreign key rather than maintaining a second identifier mapping. Null topics are valid. No network tables are invented because none were supplied. Membership deletion is restricted by referenced activity, which is sufficient for this immutable snapshot; account deletion and retention policies require a separate production design.

## Index decisions

- Primary and unique keys provide direct member/Circle lookup and slug uniqueness.
- `user_interests(user_id, topic_slug)` supports member interest reads.
- `memberships(user_id, circle_id)` supports membership fallback and eligibility exclusions without another user index.
- `memberships_circle(circle_id, role)` supports reverse member/leader lookup and future Circle detail queries.
- `circle_tags(circle_id, tag)` supports tag lookup while eliminating repeated tags in the source.
- `circles_discovery(access, last_activity_at)` supports public discovery and a future SQL recency filter; today SQL filters the activity window using `julianday` for consistent timestamp parsing, so the index helps with visibility but its timestamp part does not accelerate that expression. At 40 Circles a scan is inexpensive.
- `activity_circle_time(circle_id, created_at)` supports activity-window aggregation as data refreshes. Ranking currently uses the supplied post/chat aggregates rather than counting the partial feed sample.

SQLite CHECK constraints validate enumerated roles/formats/policies, nonnegative activity and member counts, positive capacity, and profile completeness. Capacity is allowed to be below an existing count: an over-capacity Circle is valid stored state and must be excluded from discovery.

At production size, add topic/tag reverse indexes when candidate retrieval uses those fields. Avoid extra indexes without measuring query patterns and write cost. Keep capacity aggregates consistent with authoritative membership writes, and enforce the final capacity decision in the join transaction rather than relying on a cached recommendation.
