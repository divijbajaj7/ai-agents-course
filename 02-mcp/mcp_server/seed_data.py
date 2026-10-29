"""Seed the incident database.

    python3 mcp_server/seed_data.py

Creates incidents.db next to this file: 40 synthetic incidents across 6 services,
plus runbooks and a (initially empty) tickets table. Entirely offline — the whole
point is that the classroom demo works without network access or credentials.
"""

import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path(__file__).resolve().parent / "incidents.db"

SERVICES = {
    "checkout-api":   {"team": "payments",  "tier": 1, "oncall": "payments-oncall"},
    "auth-service":   {"team": "identity",  "tier": 1, "oncall": "identity-oncall"},
    "search-indexer": {"team": "discovery", "tier": 2, "oncall": "discovery-oncall"},
    "notify-worker":  {"team": "platform",  "tier": 3, "oncall": "platform-oncall"},
    "image-resizer":  {"team": "media",     "tier": 3, "oncall": "media-oncall"},
    "billing-cron":   {"team": "payments",  "tier": 2, "oncall": "payments-oncall"},
}

RUNBOOKS = {
    "checkout-api": """# Runbook — checkout-api

## Health
`GET /healthz` returns 200 and `{"db":"ok","stripe":"ok"}`.

## Common failures

### 1. p99 latency spike (> 2s)
Almost always connection-pool exhaustion, not CPU.
1. Check `pg_stat_activity` for idle-in-transaction sessions.
2. If > 40 idle, a deploy leaked connections — roll back first, investigate second.
3. Pool size lives in `CHECKOUT_DB_POOL` (default 20). Raising it hides the leak.

### 2. 5xx burst after deploy
1. `kubectl rollout undo deploy/checkout-api` — always roll back before debugging.
2. Confirm the Stripe webhook secret rotated correctly; a stale secret gives 401→500.

### 3. Duplicate charges
SEV1, page the payments lead immediately. Do NOT retry the job.
Idempotency keys are in `checkout_attempts.idem_key`.

## Escalation
payments-oncall → payments lead → VP Eng if customer-visible for > 30 min.
""",
    "auth-service": """# Runbook — auth-service

## Health
`GET /healthz`; also verify JWKS at `/.well-known/jwks.json` is not empty.

## Common failures

### 1. Token validation failures across all clients
Usually a key rotation that did not propagate.
1. Check the JWKS endpoint returns both the old and new `kid`.
2. Overlap window is 24h — if the old key was dropped early, re-publish it.

### 2. Login latency
Rate limiter (Redis) is the usual suspect. Check `redis-cli INFO stats` for
`rejected_connections`.

### 3. Account lockout storm
Often a retry loop in a client, not an attack. Identify by user-agent before
blocking IPs.

## Escalation
identity-oncall → security on-call if you suspect credential stuffing.
""",
    "search-indexer": """# Runbook — search-indexer

## Health
Lag metric `indexer_lag_seconds` should stay under 300.

## Common failures

### 1. Index lag climbing
1. Check Kafka consumer group lag.
2. A single poison message blocks the partition — find it in the DLQ and skip it.
3. Reindex with `make reindex PARTITION=<n>`; takes ~40 min for a full partition.

### 2. Empty search results
Check the alias points at the live index, not a half-built one.
`GET /_cat/aliases?v`

## Escalation
discovery-oncall. Tier 2 — no paging outside business hours unless lag > 2h.
""",
    "notify-worker": """# Runbook — notify-worker

## Health
Queue depth under 10k; `notify_worker_up` == 1.

## Common failures

### 1. Queue backing up
1. Check the SMTP provider status page first — it is usually them.
2. Scale workers: `kubectl scale deploy/notify-worker --replicas=10`.
3. Never purge the queue. Messages are user-visible emails.

### 2. Duplicate notifications
Dedupe key is `notification.dedupe_hash`. A schema migration that changed the hash
input is the usual cause.

## Escalation
platform-oncall. Tier 3 — business hours only.
""",
    "image-resizer": """# Runbook — image-resizer

## Health
`GET /healthz`; p95 resize under 800ms.

## Common failures

### 1. OOM kills
Large source images. The limit is in `RESIZE_MAX_PIXELS` (default 40M).
Raising memory without raising the guard just moves the crash later.

### 2. Cache miss storm after deploy
The CDN key includes the build SHA. Warm the cache with `make warm-cache` before
announcing a release.

## Escalation
media-oncall. Tier 3.
""",
    "billing-cron": """# Runbook — billing-cron

## Health
Last successful run within 26 hours: check `billing_runs.finished_at`.

## Common failures

### 1. Job did not run
1. Check the scheduler lock in `billing_locks` — a crashed run leaves a stale lock.
2. Clear it ONLY after confirming no process is running. A double run double-bills.

### 2. Partial run
The job is resumable. `make billing-resume RUN_ID=<id>` — never re-run from scratch.

## Escalation
payments-oncall. Any suspected double-billing is an immediate SEV1.
""",
}

TEMPLATES = [
    ("checkout-api", "SEV1", "Checkout p99 latency spike to 4.2s",
     "Connection pool exhausted after deploy {sha}. Pool size 20, 47 idle-in-transaction "
     "sessions observed. Rolled back; latency recovered in 6 minutes.",
     "Rolled back deploy {sha}. Added a pool-leak check to CI.", "latency,database,deploy"),
    ("checkout-api", "SEV1", "5xx burst on checkout after webhook secret rotation",
     "Stale Stripe webhook secret caused 401 from the provider, surfaced as 500 to users. "
     "3,412 failed checkouts over 18 minutes.",
     "Re-synced the secret from the vault. Added an alert on webhook 401 rate.",
     "deploy,payments,5xx"),
    ("checkout-api", "SEV2", "Intermittent duplicate charge reports",
     "Idempotency key collision for retried requests sharing a cart id.",
     "Changed the key to include the attempt timestamp. Refunded 11 customers.",
     "payments,data-integrity"),
    ("auth-service", "SEV1", "Global token validation failures",
     "JWKS rotation dropped the previous kid before the 24h overlap expired. "
     "All clients holding older tokens failed validation.",
     "Re-published the previous key. Overlap window enforcement added to the rotation job.",
     "auth,jwks,rotation"),
    ("auth-service", "SEV2", "Login latency above 3s",
     "Redis rate limiter hit max connections; rejected_connections climbing.",
     "Raised the Redis connection limit and added a circuit breaker.", "latency,redis,auth"),
    ("auth-service", "SEV3", "Account lockout storm from a single client",
     "A mobile client retry loop triggered lockouts for 800 users. Not an attack.",
     "Blocked the client build, shipped a fix, released the locks.", "auth,client"),
    ("search-indexer", "SEV2", "Index lag climbed to 3 hours",
     "Poison message blocked partition 4. Consumer stalled and lag accumulated.",
     "Skipped the offending offset, reindexed partition 4.", "kafka,lag,indexing"),
    ("search-indexer", "SEV2", "Empty search results for 12 minutes",
     "Alias flipped to a half-built index during reindex.",
     "Pointed the alias back. Added a doc-count gate before alias switch.",
     "search,indexing,config"),
    ("search-indexer", "SEV3", "Slow reindex blocking a release",
     "Full reindex took 2h against an estimate of 40m due to a shared node.",
     "Moved reindex to dedicated nodes.", "indexing,capacity"),
    ("notify-worker", "SEV2", "Notification queue depth 240k",
     "Upstream SMTP provider outage; queue accumulated for 90 minutes.",
     "Waited out the provider, scaled workers to 10 to drain.", "queue,email,vendor"),
    ("notify-worker", "SEV3", "Duplicate emails sent to 4k users",
     "A migration changed dedupe_hash inputs, invalidating existing keys.",
     "Backfilled the hashes and shipped an apology email.", "email,data-integrity"),
    ("image-resizer", "SEV3", "OOM kill loop on the resizer",
     "A 120MP source image exceeded RESIZE_MAX_PIXELS but the guard ran after decode.",
     "Moved the pixel guard before decode.", "oom,memory"),
    ("image-resizer", "SEV3", "CDN cache miss storm after release",
     "Build SHA in the cache key invalidated everything at once; origin load 20x.",
     "Added cache warming to the release pipeline.", "cdn,cache,deploy"),
    ("billing-cron", "SEV1", "Billing job did not run for 31 hours",
     "A crashed run left a stale lock in billing_locks; the scheduler skipped two cycles.",
     "Cleared the lock, resumed the run. Added lock TTL and an alert on missed runs.",
     "billing,scheduler,lock"),
    ("billing-cron", "SEV2", "Partial billing run left 300 invoices unsent",
     "The pod was evicted mid-run; the resume path was never exercised.",
     "Resumed via make billing-resume. Added a resume test to CI.", "billing,resilience"),
]

STATUSES = ["resolved"] * 12 + ["monitoring", "open", "open"]


def build():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    c = con.cursor()

    c.execute("""CREATE TABLE services (
        name TEXT PRIMARY KEY, team TEXT, tier INTEGER, oncall TEXT)""")
    c.execute("""CREATE TABLE runbooks (
        service TEXT PRIMARY KEY, body TEXT)""")
    c.execute("""CREATE TABLE incidents (
        id TEXT PRIMARY KEY, service TEXT, severity TEXT, title TEXT,
        summary TEXT, resolution TEXT, tags TEXT, status TEXT,
        opened_at TEXT, resolved_at TEXT, duration_min INTEGER)""")
    c.execute("""CREATE TABLE tickets (
        id TEXT PRIMARY KEY, title TEXT, severity TEXT, service TEXT,
        body TEXT, created_at TEXT, created_by TEXT)""")

    for name, meta in SERVICES.items():
        c.execute("INSERT INTO services VALUES (?,?,?,?)",
                  (name, meta["team"], meta["tier"], meta["oncall"]))
    for svc, body in RUNBOOKS.items():
        c.execute("INSERT INTO runbooks VALUES (?,?)", (svc, body))

    rng = random.Random(1010)          # fixed seed: everyone's demo matches
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(40):
        svc, sev, title, summary, resolution, tags = TEMPLATES[i % len(TEMPLATES)]
        sha = f"{rng.randrange(16**7):07x}"
        opened = now - timedelta(days=rng.randrange(1, 180),
                                 hours=rng.randrange(24),
                                 minutes=rng.randrange(60))
        status = STATUSES[i % len(STATUSES)]
        dur = rng.choice([6, 12, 18, 24, 41, 55, 90, 126, 187])
        resolved = (opened + timedelta(minutes=dur)) if status == "resolved" else None
        rows.append((
            f"INC-{1000 + i}", svc, sev, title,
            summary.format(sha=sha), resolution.format(sha=sha) if status == "resolved" else "",
            tags, status,
            opened.strftime("%Y-%m-%d %H:%M"),
            resolved.strftime("%Y-%m-%d %H:%M") if resolved else "",
            dur if status == "resolved" else 0,
        ))
    c.executemany("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)

    con.commit()
    con.close()
    print(f"seeded {DB.name}: {len(SERVICES)} services, {len(RUNBOOKS)} runbooks, "
          f"{len(rows)} incidents")


if __name__ == "__main__":
    build()
