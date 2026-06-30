import {
  CheckCircle,
  Warning,
  XCircle,
  ArrowDown,
  Lifebuoy,
} from "@phosphor-icons/react";
import { Dialog, DialogBody } from "@/components/ui/dialog";

// "What do I do when it breaks?" guide for the Super_Admin. Opened from the
// Help button in the admin header. Pure documentation: a colour-coded decision
// flowchart + numbered steps with short explanations. Mirrors the runbook in
// the Disaster Recovery panel and infra/scripts/README.md so on-call has one
// calm place to look during an incident.

// severity → colour classes
const TONE = {
  ok: "border-emerald-300 bg-emerald-50 text-emerald-800",
  warn: "border-amber-300 bg-amber-50 text-amber-800",
  bad: "border-red-300 bg-red-50 text-red-800",
  neutral: "border-border bg-muted/50 text-foreground",
};

function Box({ tone = "neutral", title, children }) {
  return (
    <div className={`rounded-md border px-3 py-2 text-center ${TONE[tone]}`}>
      <p className="text-xs font-semibold">{title}</p>
      {children && <p className="mt-0.5 text-[11px] leading-snug opacity-90">{children}</p>}
    </div>
  );
}

function Down() {
  return (
    <div className="flex justify-center py-1 text-muted-foreground">
      <ArrowDown size={16} />
    </div>
  );
}

function Step({ n, tone = "neutral", title, children }) {
  const dot =
    tone === "bad"
      ? "bg-red-500"
      : tone === "warn"
      ? "bg-amber-500"
      : tone === "ok"
      ? "bg-emerald-500"
      : "bg-primary";
  return (
    <div className="flex gap-3">
      <div className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${dot}`}>
        {n}
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        <div className="text-xs text-muted-foreground space-y-1">{children}</div>
      </div>
    </div>
  );
}

function Code({ children }) {
  return (
    <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded bg-muted p-2 text-[11px] leading-relaxed text-foreground">
{children}
    </pre>
  );
}

export default function CrashHelpDialog({ open, onClose }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="max-w-3xl"
      title="Help — What to do when the server crashes"
      description="Stay calm and work top to bottom. The flowchart finds your situation; the steps below tell you exactly what to run."
    >
      <DialogBody className="space-y-8">
        {/* ---------------- BLAST RADIUS ---------------- */}
        <section>
          <h3 className="mb-3 text-sm font-semibold">
            If the server completely crashes — what happens
          </h3>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-md border border-red-300 bg-red-50 p-3">
              <p className="flex items-center gap-1 text-xs font-semibold text-red-700">
                <XCircle size={13} weight="fill" /> Goes down instantly
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-red-800/90">
                <li>API, dashboards, logins (all error out)</li>
                <li>All ~5,000 devices disconnect</li>
                <li>Commands &amp; telemetry stop being stored</li>
              </ul>
            </div>
            <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3">
              <p className="flex items-center gap-1 text-xs font-semibold text-emerald-700">
                <CheckCircle size={13} weight="fill" /> Survives the crash
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-emerald-800/90">
                <li>Code (in GitHub) &amp; frontend (Cloudflare Pages)</li>
                <li>Device firmware — they auto-reconnect when DNS is live</li>
                <li>Your data — <strong>only if off-site backups are ON</strong></li>
              </ul>
            </div>
          </div>

          {/* data-loss outcome */}
          <div className="mt-3 overflow-hidden rounded-md border">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-muted/60 text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Your setup</th>
                  <th className="px-3 py-1.5 font-medium">Data you lose</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                <tr className="bg-emerald-50/40">
                  <td className="px-3 py-1.5">Nightly R2 backups ON</td>
                  <td className="px-3 py-1.5">≤ 1 day — fully recoverable</td>
                </tr>
                <tr className="bg-red-50/40">
                  <td className="px-3 py-1.5">Local volume only, no off-site copy</td>
                  <td className="px-3 py-1.5 font-semibold text-red-700">
                    Everything — the disk died with it
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* recovery time */}
          <div className="mt-3 overflow-hidden rounded-md border">
            <table className="w-full text-left text-[11px]">
              <thead className="bg-muted/60 text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 font-medium">What you prepared</th>
                  <th className="px-3 py-1.5 font-medium">Time to recover</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                <tr>
                  <td className="px-3 py-1.5">Warm standby VPS</td>
                  <td className="px-3 py-1.5 text-emerald-700">~2–5 min (one command, Step 3)</td>
                </tr>
                <tr>
                  <td className="px-3 py-1.5">Backups but no standby</td>
                  <td className="px-3 py-1.5 text-amber-700">~30–60 min (new VPS + restore)</td>
                </tr>
                <tr>
                  <td className="px-3 py-1.5">Neither</td>
                  <td className="px-3 py-1.5 text-red-700">Hours–days, data lost</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Devices keep their firmware and reconnect on their own the moment <code>mqtt</code> DNS
            points at a working broker again — you never touch them individually.
          </p>
        </section>

        {/* ---------------- FLOWCHART ---------------- */}
        <section>
          <h3 className="mb-3 text-sm font-semibold">Decision flowchart</h3>
          <div className="mx-auto max-w-md">
            <Box tone="warn" title="Something looks wrong">
              Alert fired, devices offline, or a panel won&apos;t load
            </Box>
            <Down />
            <Box tone="neutral" title="Can you open the website / API health?">
              Try https://iotaps.com and /api/v1/health
            </Box>
            <Down />

            {/* branch 1: site up vs down */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="mb-1 text-center text-[11px] font-semibold text-emerald-600">
                  YES — it responds
                </p>
                <Box tone="ok" title="Likely a minor glitch">
                  One service hiccup, not a crash
                </Box>
                <Down />
                <Box tone="neutral" title="→ Step 1">
                  Restart the affected service
                </Box>
              </div>

              <div>
                <p className="mb-1 text-center text-[11px] font-semibold text-red-600">
                  NO — no response
                </p>
                <Box tone="neutral" title="Can you SSH / ping the VPS?">
                  ssh iot-bala
                </Box>
                <Down />
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="mb-1 text-center text-[10px] font-semibold text-amber-600">
                      VPS UP
                    </p>
                    <Box tone="warn" title="→ Step 2">
                      Containers down — bring them back
                    </Box>
                  </div>
                  <div>
                    <p className="mb-1 text-center text-[10px] font-semibold text-red-600">
                      VPS DEAD
                    </p>
                    <Box tone="bad" title="→ Step 3">
                      Fail over / rebuild
                    </Box>
                  </div>
                </div>
              </div>
            </div>

            <Down />
            <Box tone="neutral" title="→ Step 4: Verify & repoint DNS">
              Confirm health, point devices at the live box
            </Box>
          </div>
        </section>

        {/* ---------------- STEPS ---------------- */}
        <section className="space-y-5">
          <h3 className="text-sm font-semibold">Step-by-step</h3>

          <Step n="0" tone="ok" title="Before anything: don't panic, don't delete">
            <p>
              <CheckCircle size={12} className="mr-1 inline text-emerald-500" />
              Your data is safe as long as you never run <code>docker compose down -v</code> (the
              <code> -v</code> deletes the database). If you have off-site backups in R2, even a
              dead server loses at most one night of data.
            </p>
          </Step>

          <Step n="1" tone="warn" title="Website responds → restart the one bad service">
            <p>Check what&apos;s unhealthy, then restart just that container. The rest keep running.</p>
            <Code>{`cd ~/projects/iotaps
docker compose ps                 # find the one that's restarting/exited
docker logs iotaps-<name> --tail 50
docker compose restart <name>     # e.g. mosquitto, fastapi-api`}</Code>
            <p>
              <Warning size={12} className="mr-1 inline text-amber-500" />
              If RAM or disk is near 100% (see Disaster Recovery panel), that&apos;s the real cause —
              free space / restart Redis before it crashes again.
            </p>
          </Step>

          <Step n="2" tone="warn" title="VPS reachable but site down → bring the stack up">
            <p>The box is alive; the containers stopped (reboot, OOM, etc.). Start them all back up.</p>
            <Code>{`cd ~/projects/iotaps
docker compose up -d              # NEVER add -v
docker logs iotaps-postgres --tail 50
curl -s http://localhost:8000/api/v1/health`}</Code>
            <p>If the database looks corrupted, restore the latest backup instead:</p>
            <Code>{`bash infra/scripts/restore-from-r2.sh`}</Code>
          </Step>

          <Step n="3" tone="bad" title="VPS dead / unreachable → fail over or rebuild">
            <p>
              <XCircle size={12} className="mr-1 inline text-red-500" />
              The server itself is gone (hardware, network, Contabo outage). No command on that box
              can help — you move to another machine.
            </p>
            <p className="font-medium text-foreground">If you have a standby VPS (recommended):</p>
            <Code>{`# on the STANDBY box:
cd ~/projects/iotaps
bash infra/scripts/promote-standby.sh`}</Code>
            <p>This restores the latest R2 backup, starts the stack, and flips DNS automatically.</p>
            <p className="font-medium text-foreground">If you have no standby (rebuild fresh):</p>
            <Code>{`# on a NEW Contabo VPS (full steps in firmware/deploy.txt):
git clone https://github.com/TheVasuA/iotaps.git && cd iotaps
nano .env                         # paste saved secrets
docker compose up -d postgres
bash infra/scripts/restore-from-r2.sh
docker compose up -d
docker exec -w /srv/app iotaps-api alembic upgrade head`}</Code>
          </Step>

          <Step n="4" tone="ok" title="Verify and repoint devices">
            <p>Confirm everything is healthy, then make sure devices know where to connect.</p>
            <Code>{`docker compose ps
curl -s http://localhost:8000/api/v1/health   # expect {"status":"ok"}`}</Code>
            <p>
              In Cloudflare DNS, point the <code>api</code> and <code>mqtt</code> A-records at the
              live server&apos;s IP (keep them grey-cloud / DNS-only, TTL 60s).
              <code>promote-standby.sh</code> does this for you if the Cloudflare keys are set.
              Devices reconnect on their own within 1–2 minutes once DNS propagates.
            </p>
          </Step>
        </section>

        {/* ---------------- PREVENT ---------------- */}
        <section className="rounded-md border border-dashed p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Lifebuoy size={16} className="text-primary" />
            Prevent the next incident
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            <li>Turn on nightly off-site backups: <code>sudo bash infra/scripts/install-backup-cron.sh</code></li>
            <li>Keep a warm standby VPS ready so Step 3 is one command, not an hour.</li>
            <li>Watch RAM/disk in the <strong>Disaster Recovery</strong> panel — they fill up before a crash.</li>
            <li>Always take a backup before deploying (Controls panel → Backup &amp; Download).</li>
          </ul>
        </section>
      </DialogBody>
    </Dialog>
  );
}
