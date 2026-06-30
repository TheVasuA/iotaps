import { useState } from "react";
import { toast } from "sonner";
import {
  Terminal,
  Copy,
  Check,
  Plugs,
  Cube,
  ArrowsClockwise,
  Database,
  CloudArrowUp,
  Broadcast,
  ShieldCheck,
  Warning,
} from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";

// Admin command reference (ops cheat-sheet). Pure documentation: every command
// the operator commonly needs — SSH, Docker, DB backup/restore, off-site backup
// + failover, MQTT testing, firewall — grouped with short "why" notes and
// one-click copy. Sourced from commands.txt, firmware/deploy.txt and
// infra/scripts/*. No backend; this is a static, safe reference.
//
// NOTE: commands run on the VPS shell over SSH. The platform itself can't run
// host-level docker/ssh from the browser, so these are copy-and-paste.

// --- one command row with copy button ---------------------------------------
function Cmd({ note, cmd, danger = false }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(true);
      toast.success("Copied");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Copy failed — select and copy manually");
    }
  };
  return (
    <div className="space-y-1">
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      <div
        className={`group flex items-start justify-between gap-2 rounded-md border p-2 ${
          danger ? "border-red-300 bg-red-50/50" : "bg-muted/40"
        }`}
      >
        <pre className="overflow-x-auto whitespace-pre-wrap break-all text-xs leading-relaxed">
{cmd}
        </pre>
        <button
          onClick={copy}
          title="Copy"
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground"
        >
          {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
        </button>
      </div>
    </div>
  );
}

// --- a titled section card ---------------------------------------------------
function Section({ icon: Icon, title, description, children, danger = false }) {
  return (
    <Card className={danger ? "border-red-300" : undefined}>
      <CardHeader>
        <CardTitle className={`text-base flex items-center gap-2 ${danger ? "text-red-600" : ""}`}>
          <Icon size={18} />
          {title}
        </CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  );
}

export default function CommandsReferencePanel() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Terminal size={20} className="text-primary" />
            Server Command Reference
          </CardTitle>
          <CardDescription>
            Copy-paste cheat sheet for operating the VPS over SSH. These run in the server shell
            (not the browser). Project lives at <code>~/projects/iotaps</code>. Container names:
            <code className="mx-1">iotaps-api</code>,<code className="mx-1">iotaps-ws</code>,
            <code className="mx-1">iotaps-workers</code>,<code className="mx-1">iotaps-nginx</code>,
            <code className="mx-1">iotaps-mosquitto</code>,<code className="mx-1">iotaps-postgres</code>,
            <code className="mx-1">iotaps-redis</code>.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* SSH / ACCESS */}
      <Section
        icon={Plugs}
        title="SSH & Server Access"
        description="Get into the VPS. If password login keeps re-prompting, root password auth is likely disabled — use the Contabo VNC console to fix sshd."
      >
        <Cmd note="Connect (uses your ~/.ssh/config 'iot-bala' host)." cmd="ssh iot-bala" />
        <Cmd note="Connect directly by IP as root." cmd="ssh root@94.136.184.17" />
        <Cmd
          note="Diagnose 'password keeps asking': verbose handshake shows which auth methods the server allows."
          cmd="ssh -v -o PreferredAuthentications=password -o PubkeyAuthentication=no root@94.136.184.17"
        />
        <Cmd
          note="On the server: check whether root/password login is enabled (last matching line wins)."
          cmd={`grep -r -i "PasswordAuthentication\\|PermitRootLogin" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/`}
        />
        <Cmd note="Apply sshd changes." cmd="systemctl restart ssh || systemctl restart sshd" />
        <Cmd note="Go to the project directory (most commands below assume you are here)." cmd="cd ~/projects/iotaps" />
      </Section>

      {/* DOCKER STATUS */}
      <Section
        icon={Cube}
        title="Docker — Status & Logs"
        description="Inspect and troubleshoot running services. Safe, read-only."
      >
        <Cmd note="List all services and their state (up/restarting/exited)." cmd="docker compose ps" />
        <Cmd note="Live resource usage per container (RAM/CPU) — watch for the Redis OOM that caused the past crash." cmd="docker stats --no-stream" />
        <Cmd note="Tail logs for one service (swap the name)." cmd="docker logs iotaps-api --tail 100 -f" />
        <Cmd note="Mosquitto broker logs — confirm it's listening and devices connect." cmd="docker logs iotaps-mosquitto --tail 50" />
        <Cmd note="Restart a single service without touching the rest." cmd="docker compose restart mosquitto" />
        <Cmd note="Health check from inside the box." cmd="curl -s http://localhost:8000/api/v1/health" />
      </Section>

      {/* DEPLOY / UPDATE */}
      <Section
        icon={ArrowsClockwise}
        title="Deploy & Update (Backend)"
        description="Safe rolling update. Frontend deploys itself via Cloudflare Pages on git push. ALWAYS back up first (see below)."
      >
        <Cmd note="1. Pull the latest code." cmd={`cd ~/projects/iotaps\ngit pull origin main`} />
        <Cmd note="2. Rebuild only the app image (DB/Redis/MQTT untouched)." cmd="docker compose build fastapi-api" />
        <Cmd
          note="3. Restart only the app containers (no --deps, so data services stay up)."
          cmd="docker compose up -d --no-deps fastapi-api fastapi-ws workers nginx"
        />
        <Cmd note="4. Apply DB migrations (additive — never drops data)." cmd="docker exec -w /srv/app iotaps-api alembic upgrade head" />
        <Cmd
          note="Rebuilt the Dockerfile (e.g. added pg client)? Force a clean rebuild instead of step 2."
          cmd="docker compose build --no-cache fastapi-api"
        />
      </Section>

      {/* DB BACKUP / RESTORE */}
      <Section
        icon={Database}
        title="Database — Backup & Restore (local)"
        description="On-box pg_dump/pg_restore. For one-click versions, use the Controls and Disaster Recovery panels."
      >
        <Cmd
          note="Quick backup before any deploy (custom format, restorable)."
          cmd={`docker exec -t iotaps-postgres pg_dump -U iotaps -d iotaps -Fc -f /tmp/pre_deploy.dump\ndocker cp iotaps-postgres:/tmp/pre_deploy.dump ./backups/`}
        />
        <Cmd
          note="Pull a dump down to your Windows machine (run in PowerShell, not on the VPS)."
          cmd="scp root@94.136.184.17:/projects/iotaps/backups/*.dump D:\\iotaps-backups\\"
        />
        <Cmd
          note="Restore a dump into the running DB."
          danger
          cmd={`docker cp ./backups/your_backup.dump iotaps-postgres:/tmp/restore.dump\ndocker exec -t iotaps-postgres pg_restore --clean --if-exists -U iotaps -d iotaps /tmp/restore.dump`}
        />
      </Section>

      {/* OFF-SITE BACKUP + FAILOVER */}
      <Section
        icon={CloudArrowUp}
        title="Off-site Backup & Standby Failover"
        description="Scripts in infra/scripts/. Set the BACKUP_R2_* keys in .env first (see infra/scripts/README.md)."
      >
        <Cmd note="Install the AWS CLI (needed to talk to R2)." cmd="sudo apt update && sudo apt install -y awscli curl" />
        <Cmd note="Run one off-site backup now (uploads a .dump to Cloudflare R2)." cmd="bash infra/scripts/backup-to-r2.sh" />
        <Cmd note="Schedule the nightly backup cron (default 03:15 daily)." cmd="sudo bash infra/scripts/install-backup-cron.sh" />
        <Cmd note="Check the backup log." cmd="tail -n 50 /var/log/iotaps-backup.log" />
        <Cmd note="Restore the latest off-site backup." danger cmd="bash infra/scripts/restore-from-r2.sh" />
        <Cmd
          note="Promote THIS box to primary after the old one died (restores + starts + flips DNS)."
          danger
          cmd="bash infra/scripts/promote-standby.sh"
        />
      </Section>

      {/* MQTT */}
      <Section
        icon={Broadcast}
        title="MQTT / Device Testing"
        description="Publish commands to a device and watch its telemetry. Replace the device token in the topic."
      >
        <Cmd
          note="Turn LED1 ON (example command payload)."
          cmd={`docker exec iotaps-mosquitto mosquitto_pub -t "iotaps/dT_cDW3aix7/command" -m "{\\"type\\":\\"toggle\\",\\"target\\":\\"led1\\",\\"value\\":1,\\"command_id\\":\\"test1\\"}"`}
        />
        <Cmd
          note="Watch what a device is publishing (telemetry stream)."
          cmd={`docker exec iotaps-mosquitto mosquitto_sub -t "iotaps/dT_cDW3aix7/telemetry" -v`}
        />
        <Cmd note="Register an MQTT node so devices can be assigned to it (post-deploy)." cmd={`curl -X POST http://localhost:8000/api/v1/admin/mqtt-nodes -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"ip":"mosquitto","port":1883,"capacity":10000}'`} />
      </Section>

      {/* FIREWALL / SYSTEM */}
      <Section
        icon={ShieldCheck}
        title="Firewall & System"
        description="Ports the platform needs: 22 (SSH), 80/443 (web), 1883 (MQTT), 9001 (MQTT over WS)."
      >
        <Cmd note="Open the required ports." cmd={`sudo ufw allow 22/tcp\nsudo ufw allow 80/tcp\nsudo ufw allow 443/tcp\nsudo ufw allow 1883/tcp\nsudo ufw allow 9001/tcp`} />
        <Cmd note="Enable the firewall / check status." cmd="sudo ufw --force enable && sudo ufw status" />
        <Cmd note="Disk usage — a full disk is a top crash cause; watch this." cmd="df -h /" />
        <Cmd note="Issue / renew SSL certs (Let's Encrypt via nginx)." cmd="sudo certbot --nginx -d api.iotaps.com -d iotaps.com -d www.iotaps.com" />
      </Section>

      {/* DANGER ZONE */}
      <Section
        icon={Warning}
        title="Danger Zone"
        description="Destructive. Read twice. Always have an off-site backup first."
        danger
      >
        <Cmd
          note="NEVER use -v in normal operation: the -v flag DELETES your data volumes (DB, Redis, MQTT)."
          danger
          cmd="docker compose down          # OK (keeps volumes).  AVOID: docker compose down -v"
        />
        <Cmd
          note="Full wipe & redeploy — destroys ALL data. Only on a throwaway/fresh setup."
          danger
          cmd={`docker compose down -v --rmi all\ndocker system prune -af --volumes`}
        />
      </Section>
    </div>
  );
}
