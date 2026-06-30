# IoTAPS Ops Scripts — Off-site Backup & Standby Failover

These scripts give the single-VPS deployment two things it otherwise lacks:
**off-site backups** (so a dead disk/server doesn't lose data) and **fast
failover** (so a dead VPS means minutes of downtime, not hours).

| Script | Run on | Purpose |
|---|---|---|
| `backup-to-r2.sh` | primary VPS (via cron) | pg_dump → upload to Cloudflare R2 → prune old copies |
| `install-backup-cron.sh` | primary VPS (once) | register the nightly backup cron job |
| `restore-from-r2.sh` | any VPS | download a backup from R2 and restore it |
| `promote-standby.sh` | standby VPS | one-command promotion: restore + start + DNS flip |

## 1. Prerequisites

On each VPS that runs these:

```bash
sudo apt update && sudo apt install -y awscli curl
# (docker + the iotaps stack are already installed per firmware/deploy.txt)
```

## 2. Create the R2 bucket + token (Cloudflare)

1. Cloudflare dashboard → **R2** → create a bucket, e.g. `iotaps-backups`.
2. **R2 → Manage API Tokens** → create a token with **Object Read & Write** on
   that bucket. Note the Access Key ID, Secret, and the S3 endpoint
   (`https://<accountid>.r2.cloudflarestorage.com`).
3. Add the keys to the VPS `.env` (see the "Off-site backups" block in
   `.env.example`).

## 3. Enable nightly backups (primary VPS)

```bash
cd /projects/iotaps
# fill in BACKUP_R2_* in .env first, then:
bash infra/scripts/backup-to-r2.sh        # one-off test — should upload a .dump
sudo bash infra/scripts/install-backup-cron.sh
```

Verify the next morning: `tail -n 50 /var/log/iotaps-backup.log` and check the
object appears in the R2 bucket under `db/`.

Optional dead-man's switch: set `BACKUP_HEALTHCHECK_URL` to a
[healthchecks.io](https://healthchecks.io) ping URL — you get alerted if a
nightly backup ever fails to run.

## 4. Standby server (warm spare)

Set up a second cheap VPS exactly like the primary (clone repo, copy the **same**
`.env`, `docker compose up -d`), then leave it idle. It costs little and is ready.

When the primary dies, on the **standby**:

```bash
cd /projects/iotaps
bash infra/scripts/promote-standby.sh
```

This restores the latest R2 backup, starts the full stack, runs migrations, and
— if `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ZONE_ID` / `FAILOVER_DNS_RECORDS` are
set in `.env` — repoints the `api` and `mqtt` DNS records to the standby's IP at
TTL 60. Devices reconnect automatically once DNS propagates (~1–2 min).

> Keep your `api`/`mqtt` DNS records **grey-cloud (DNS only)** and at a low TTL
> (60s) so failover is fast. This matches `firmware/deploy.txt`.

## 5. Manual restore (any time)

```bash
bash infra/scripts/restore-from-r2.sh                      # latest backup
bash infra/scripts/restore-from-r2.sh db/iotaps_2026....dump  # a specific one
```

## Recovery decision tree

```
Container crashed, VPS up?   → docker compose up -d         (self-heals anyway)
VPS up but DB corrupted?     → restore-from-r2.sh
VPS dead / unreachable?      → promote-standby.sh  on the spare
No standby yet?              → new VPS per deploy.txt, then restore-from-r2.sh
```

## Notes / limits

- **RPO** (max data loss) = time since last nightly backup. For tighter RPO,
  run the cron more often (e.g. every 6h) or add streaming replication later.
- `pg_restore --clean` may print ignorable "does not exist, skipping" notices;
  hard errors are surfaced by the scripts.
- These scripts are for the current single-primary topology. The long-term
  zero-downtime path is a managed/replicated Postgres + 2 app nodes behind a
  load balancer (see the Disaster Recovery panel in the admin UI).
```
