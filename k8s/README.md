# IoTAPS on Kubernetes

Kustomize manifests for the IoTAPS backend: the REST API, the WebSocket gateway,
the background worker bundle, and the three stateful dependencies
(PostgreSQL + TimescaleDB, Redis, Mosquitto).

These are a translation of `docker-compose.yml`, not a replacement for it. The
Compose stack remains the documented single-VPS deployment path (see
`DEPLOY.md`); this directory is for running the same workloads on a cluster.

## Layout

```
k8s/
  base/                     complete stack, sane defaults, no Secret
    config/
      app.env               non-secret settings -> iotaps-config ConfigMap
      supervisord.conf      k8s copy of infra/supervisor/supervisord.conf
      redis.conf            memory cap + LRU eviction
      mosquitto.conf        k8s copy of infra/mosquitto/mosquitto.conf
    postgres.yaml           StatefulSet + headless Service + PVC
    redis.yaml              StatefulSet + headless Service + PVC
    mosquitto.yaml          StatefulSet + ClusterIP Service + PVC
    job-migrate.yaml        alembic upgrade head
    api.yaml                Deployment + Service (:8000)
    ws.yaml                 Deployment + Service (:8001)
    workers.yaml            Deployment (1 replica, supervisord)
    ingress.yaml            two Ingresses: /api (60s) and /ws (3600s)
    hpa.yaml                autoscaling for api and ws
    pdb.yaml                disruption budgets for api and ws
    networkpolicy.yaml      optional, NOT in the kustomization by default
  overlays/
    dev/                    1 replica per tier, small volumes, no HPA/PDB/LB
    prod/                   real host, pinned image, MQTT LoadBalancer, SSD class
```

## Deploy

Everything goes through Kustomize. `kubectl apply -f base/` will not work: the
ConfigMaps and the Secret are generated, not committed.

```bash
# 1. Build and push the image. One image serves all three tiers.
docker build -t ghcr.io/<org>/iotaps-api:$(git rev-parse --short HEAD) ./app
docker push   ghcr.io/<org>/iotaps-api:$(git rev-parse --short HEAD)

# 2. Point the overlay at it (edit the `images:` block).
$EDITOR k8s/overlays/prod/kustomization.yaml

# 3. Create the Secret input. Gitignored; never commit it.
cd k8s/overlays/prod
cp secrets.env.example secrets.env
$EDITOR secrets.env

# 4. Review the rendered output, then apply.
kubectl kustomize k8s/overlays/prod | less
kubectl apply -k k8s/overlays/prod
```

Local cluster:

```bash
docker build -t iotaps/api:dev ./app
kind load docker-image iotaps/api:dev      # kind; see below for MicroK8s
cp k8s/overlays/dev/secrets.env.example k8s/overlays/dev/secrets.env
kubectl apply -k k8s/overlays/dev
kubectl -n iotaps port-forward svc/iotaps-api 8000:8000
curl localhost:8000/api/v1/health
```

### MicroK8s

Verified end to end on MicroK8s v1.36.2 — the whole stack runs. Three
differences from the generic instructions above.

```bash
# 1. Addons. hostpath-storage is mandatory: the StatefulSets request no
#    storageClassName, so without a cluster default their PVCs stay Pending.
#    dns is usually on already. Skip metallb; skip metrics-server unless you want
#    `kubectl top` (the dev overlay deletes the HPAs, so nothing needs it).
microk8s enable dns hostpath-storage
microk8s config > ~/.kube/config          # so plain kubectl/kustomize work

# 2. Image loading. MicroK8s has its own containerd store, so `docker build`
#    alone is not enough and there is no `kind load` equivalent.
docker build -t iotaps/api:dev ./app
docker save iotaps/api:dev -o /tmp/iotaps-api-dev.tar
microk8s images import < /tmp/iotaps-api-dev.tar
microk8s ctr images ls | grep iotaps      # expect docker.io/iotaps/api:dev
rm /tmp/iotaps-api-dev.tar                # ~200MB

# 3. Apply.
cp k8s/overlays/dev/secrets.env.example k8s/overlays/dev/secrets.env
$EDITOR k8s/overlays/dev/secrets.env
microk8s kubectl apply -k k8s/overlays/dev
microk8s kubectl -n iotaps get pods -w
```

`imagePullPolicy: IfNotPresent` in the base is what makes the imported image
resolve; with `Always` the nodes would try to pull `iotaps/api:dev` from Docker
Hub and fail. Note that `microk8s images import` prints
`Pushing OCI images to <node-ip>:25000` — that is its internal registry mirror,
not an outbound upload.

Cold start takes about 2.5 minutes: Postgres runs initdb plus the TimescaleDB
extension setup, the migration Job waits on that, and the app tiers wait on the
migration through their `wait-for-migrations` initContainer.

#### Sharing a host with an existing web server

> **`microk8s enable ingress` will hijack ports 80 and 443 from anything already
> using them, silently.** Check before you enable it.

The addon's controller runs with `hostPort: 80` and `hostPort: 443`. The CNI
portmap chain that implements those inserts iptables DNAT rules that take
precedence over Docker's published-port rules, so an existing container
publishing `0.0.0.0:80` keeps its listening socket and keeps looking healthy
while every incoming request is routed to the ingress controller instead. `ss`
still shows `docker-proxy` bound to :80, which makes it easy to misread. The only
symptom is that the other site starts returning the ingress controller's 404.

This was hit on exactly that setup here: enabling the addon took down a co-hosted
site for ~33 minutes with no visible error anywhere.

Check first:

```bash
ss -tlnp | grep -E ':80 |:443 '
docker ps --format '{{.Names}}\t{{.Ports}}'
```

If something already owns 80/443, do not use the addon. Install ingress-nginx as
a NodePort service instead — it never touches privileged ports, and as a bonus it
is the controller these manifests' annotations actually target:

```bash
microk8s helm3 repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
microk8s helm3 repo update
microk8s helm3 install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --set controller.replicaCount=1 \
  --set controller.service.type=NodePort \
  --set controller.service.nodePorts.http=30080 \
  --set controller.service.nodePorts.https=30443 \
  --set controller.hostPort.enabled=false \
  --set controller.hostNetwork=false \
  --set controller.ingressClassResource.name=nginx \
  --set controller.ingressClassResource.default=false \
  --set controller.watchIngressWithoutClass=false \
  --wait
```

Verify it grabbed nothing privileged, and that the incumbent still answers:

```bash
microk8s kubectl -n ingress-nginx get deploy ingress-nginx-controller \
  -o jsonpath='{range .spec.template.spec.containers[*].ports[*]}{.name}={.hostPort} {end}'
curl -sI -H 'Host: <the-other-site>' http://127.0.0.1/ | head -3
```

The cost is that the app is served on `:30080` rather than `:80`, so
`PUBLIC_BASE_URL` has to carry the port. To get a clean port-80 URL while another
service owns it, add a vhost to *that* server proxying your hostname to
`127.0.0.1:30080` — which keeps it in charge of 80/443 and its own certificates.

This path was verified end to end on `dev.iotaps.com`: `/api/v1/health`,
`/api/v1/docs` and `/api/v1/openapi.json` all return 200 through the controller,
and an idle WebSocket on `/ws` survived 150s. Because this is genuine
ingress-nginx, the generated config can be inspected to prove the per-path
timeout split is real:

```bash
POD=$(microk8s kubectl -n ingress-nginx get pod \
  -l app.kubernetes.io/component=controller -o name | head -1)
microk8s kubectl -n ingress-nginx exec $POD -- grep -n 'location \|proxy_read_timeout' /etc/nginx/nginx.conf
```

`location = "/ws"` carries `proxy_read_timeout 3600s` while `/api` gets `60s` —
which is the whole reason `ingress.yaml` splits the two paths across separate
Ingress objects.

#### The ingress addon controller

**The ingress addon is Traefik, not ingress-nginx**, as of MicroK8s 1.35. It
registers three IngressClasses — `nginx`, `public` (default) and `traefik` — all
backed by `traefik.io/ingress-controller`, so `ingressClassName: nginx` in these
manifests is adopted by Traefik through its NGINX-compatibility provider.
Measured on 1.36.2: `/api` routing works, and an idle WebSocket with client
pings disabled survived 240s and still answered a ping afterwards, clearing
Traefik's 180s default `idleTimeout`. So the WebSocket tier works under the addon
too — but not because of the `nginx.ingress.kubernetes.io/proxy-read-timeout`
annotation, whose effect under Traefik is unconfirmed. Under real ingress-nginx
the annotation demonstrably drives it (see the section above).

Its `traefik` Service is type `LoadBalancer`, so without MetalLB the
`EXTERNAL-IP` stays `<pending>` indefinitely. Do not read that as "the addon
failed to take port 80" — the two are unrelated. The hostPort binding happens at
the iptables layer and succeeds regardless, which is exactly what makes the
port-80 hijack described above so easy to miss.

Two MicroK8s caveats on storage. `microk8s-hostpath` uses
`WaitForFirstConsumer`, so PVCs sit Pending until their pod schedules — that is
normal, not a fault. And it enforces no size limit: the 5Gi/1Gi/1Gi in
`patch-dev-storage.yaml` are advisory, data lands in
`/var/snap/microk8s/common/default-storage`, and Postgres can fill the root disk.

#### The dev hostname

`overlays/dev` is configured for **`dev.iotaps.com`** in two places that must stay
in step:

| Setting | File | Value |
|---|---|---|
| Ingress `host` (both objects) | `patch-dev-ingress.yaml` | `dev.iotaps.com` |
| `PUBLIC_BASE_URL` | `patch-dev-config.yaml` | `http://dev.iotaps.com` |
| `CORS_ALLOW_ORIGINS` | `patch-dev-config.yaml` | explicit origins, not `*` |

`PUBLIC_BASE_URL` must match how the app is actually reached, port included. With
the ingress controller on `hostPort: 80` a bare hostname is right; if you move it
back to NodePort-only it has to become `http://dev.iotaps.com:30080`. This value
feeds emailed links, public dashboard URLs and webhook callbacks, so a mismatch
produces links that 404 rather than an obvious failure.

`CORS_ALLOW_ORIGINS` is an explicit list rather than `*` because the app sets
`allow_credentials=True`, and browsers reject a wildcard on credentialed
requests — a `*` here silently breaks the SPA's authenticated calls.

DNS needs a single A record; `/api` and `/ws` are two paths on the same host:

| Type | Name | Content | Cloudflare proxy |
|---|---|---|---|
| A | `dev` | the node's public IP | **DNS only (grey)** |

Smoke test:

```bash
curl http://dev.iotaps.com/api/v1/health
open http://dev.iotaps.com/api/v1/docs
```

Verified on this setup over HTTPS with a trusted certificate: `/` serves the SPA,
`/login` and `/dashboard/42` return 200 (SPA fallback), hashed assets return 200
with `max-age=31536000`, `/api/v1/health` and `/api/v1/docs` return 200, HTTP
redirects with a 308, and an idle `wss://dev.iotaps.com/ws` connection validated
against the system trust store and survived 75s with no client pings.

#### TLS with cert-manager

```bash
microk8s enable cert-manager
microk8s kubectl apply -f k8s/cluster-issuers.yaml
microk8s kubectl get clusterissuer            # both should report READY=True
```

The dev Ingresses carry `cert-manager.io/cluster-issuer` and a `tls` block;
cert-manager does the rest. Watch an issuance with:

```bash
microk8s kubectl -n iotaps get certificate,certificaterequest,order,challenge
```

Four things worth knowing:

- **All three Ingresses share one secret** (`iotaps-dev-tls`) because they serve
  one hostname. cert-manager de-duplicates, so exactly one certificate is issued.
  Giving them separate secret names would request three certificates for the same
  name and eat into the rate limit for no benefit.
- **HTTP-01 depends on port 80.** Let's Encrypt fetches
  `http://<host>/.well-known/acme-challenge/<token>`, so the controller must be
  reachable on :80 from the internet. If it is NodePort-only on :30080, HTTP-01
  cannot work — use the DNS-01 solver instead. The solver Ingress uses an exact
  path, so it takes precedence over the SPA's `/` catch-all.
- **Validate with staging first.** Production allows only 5 failed validations per
  hostname per hour. Flip the annotation to `letsencrypt-staging`, confirm the
  Certificate goes Ready, then switch to `letsencrypt-prod`. Switching issuers
  needs the old Secret and Certificate deleted, or cert-manager keeps serving the
  existing cert:
  ```bash
  microk8s kubectl -n iotaps delete secret,certificate iotaps-dev-tls
  ```
  Measured here: staging Ready in 35s, production in 20s.
- **The HTTP→HTTPS redirect is automatic** once `tls` is present — ingress-nginx
  returns a 308. This applies to `/ws` too, which is correct: the SPA derives
  `wss://` from the page origin, so everything lands on TLS. Renewal is automatic
  at roughly two-thirds of the 90-day lifetime, with no restart needed.

#### The SPA is served in-cluster in dev only

`base` routes only `/api` and `/ws`, because production hosts the frontend on
Cloudflare Pages. That leaves the root of the hostname returning a bare 404,
which looks like the app is down. The dev overlay therefore adds a web tier:

| File | Purpose |
|---|---|
| `web.yaml` | SPA Deployment + Service (`iotaps/web:dev`, nginx on 8080) |
| `ingress-web.yaml` | third Ingress: `/` (Prefix) → `iotaps-web` |
| `config/web-nginx.conf` | the SPA rewrite the image does not ship |

Two things make this necessary rather than cosmetic. First, the web image bakes
in **no** nginx config — Compose mounts `infra/nginx/*` instead — so it falls back
to nginx's stock default with no `try_files`, and every deep link or browser
refresh on a client-side route 404s. The ConfigMap supplies that rewrite. Second,
nginx listens on 8080, not 80, because the pod runs as uid 101 and a non-root
process cannot bind a privileged port.

Path precedence is unambiguous: ingress-nginx sorts by descending specificity, so
`/api` and `/ws` are matched before the `/` catch-all. Verified after adding the
web tier — `/ws` still gets its 3600s timeout rather than the web Ingress's 30s.

Build and load it separately from the API image:

```bash
docker build -t iotaps/web:dev ./web
docker save iotaps/web:dev | microk8s images import
```

The bundle needs no rebuild per hostname: `web/.env.production` leaves
`VITE_API_BASE_URL` relative at `/api/v1` and `realtime.js` derives
`wss://<current-host>/ws`, so same-origin hosting works on any hostname and
avoids CORS entirely. To host the frontend in-cluster in production too, move
`web.yaml` and `config/web-nginx.conf` into `base`, add the `/` path there, and
drop the Cloudflare Pages step.

To put the controller on ports 80/443 — only do this when nothing else on the
host owns them:

```bash
microk8s helm3 upgrade ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --set controller.replicaCount=1 \
  --set controller.service.type=NodePort \
  --set controller.service.nodePorts.http=30080 \
  --set controller.service.nodePorts.https=30443 \
  --set controller.hostPort.enabled=true \
  --set controller.hostPort.ports.http=80 \
  --set controller.hostPort.ports.https=443 \
  --set controller.hostNetwork=false \
  --set controller.ingressClassResource.name=nginx \
  --set controller.ingressClassResource.default=false \
  --set controller.watchIngressWithoutClass=false --wait
```

The NodePorts keep working alongside the hostPorts, so `:30080` stays available
as a fallback. Note that `ss -tlnp` shows **no listener** on 80/443 even when this
is working — hostPort is implemented with iptables DNAT, not a socket. That is
also precisely why the hijack described above is so easy to miss, in either
direction: bringing a Docker container that publishes `:80` back up while this is
active will not produce a clear error, it will just quietly lose.

To remove everything afterwards:

```bash
microk8s kubectl delete -k k8s/overlays/dev   # keeps the PVCs
microk8s kubectl -n iotaps delete pvc --all   # deletes the data
snap remove microk8s                          # removes the cluster
```

## Before you apply: things to change

| Placeholder | Where | Notes |
|---|---|---|
| `ghcr.io/REPLACE_ME/iotaps-api` | `overlays/prod/kustomization.yaml` | registry and an immutable tag |
| `REPLACE_ME_*` | `overlays/*/secrets.env` | generate with `openssl rand -hex 32` |
| `api.iotaps.example.com` | `overlays/prod/patch-ingress-host.yaml`, `kustomization.yaml` | must match `PUBLIC_BASE_URL` |
| `fast-ssd` | `overlays/prod/patch-storage.yaml` | must be a real StorageClass |
| `letsencrypt-prod` | `overlays/prod/patch-ingress-host.yaml` | must be a real ClusterIssuer |

Cluster prerequisites: an ingress controller (the annotations assume
ingress-nginx), a default StorageClass supporting `ReadWriteOnce`, and
metrics-server if you want the HPAs to function.

### Measured idle footprint

From the MicroK8s run of `overlays/dev` (1 replica per tier, nothing connected):

| Tier | CPU | Memory |
|---|---|---|
| api | 4m | 101Mi |
| ws | 5m | 102Mi |
| workers | 48m | 500Mi |
| postgres | 9m | 56Mi |
| redis | 16m | 9Mi |
| mosquitto | 1m | 1Mi |
| **total** | **~83m** | **~770Mi** |

The workers pod dominates because it holds 11 Python interpreters, each with its
own SQLAlchemy pool. Including MicroK8s' own system pods the node showed 950m of
CPU requests and 1550Mi of memory requests, so a 2 vCPU / 4GB box runs the dev
stack with room to spare.

## Operational constraints

These are properties of the application, not choices made in the manifests.
Changing them requires changing application code.

### The workers Deployment must stay at 1 replica

Every program in `supervisord.conf` is a singleton. `mqtt_listener` holds a
wildcard MQTT subscription across all orgs, `batch_writer` drains one shared
Redis ingest queue, and `downsampler` / `data_retention` / `subscription_expiry`
/ `stats_publisher` / `session_cleanup` are interval loops with no leader
election. A second replica double-ingests telemetry and double-fires every
scheduled job.

This is why `workers.yaml` uses `strategy: Recreate` (a rolling update would
briefly run two listeners) and why it has no HPA and no PodDisruptionBudget. To
scale one worker independently, split it out of `supervisord.conf` into its own
Deployment, or move the schedulers to CronJobs.

### Postgres connection budget

`app/db/session.py` hardcodes `pool_size=10, max_overflow=20`, so **every
process** can hold 30 connections, and the value is not configurable through the
environment. The worst case is:

```
api:     replicas x API_WORKERS x 30
ws:      replicas x WS_WORKERS  x 30
workers: 1 x 11 processes       x 30   = 330
migrate: 1 (NullPool)
```

With the base defaults (2 api replicas x 2 workers, 2 ws replicas x 2 workers)
that is 120 + 120 + 330 = 570 against `max_connections=300`. In practice
SQLAlchemy opens connections lazily and the worker loops are mostly idle, so
steady state is far below the ceiling, but a traffic burst can exhaust it and
`pool_timeout=30` then surfaces as 30-second request stalls.

If you scale past the defaults, put PgBouncer in front of Postgres (transaction
pooling) rather than raising `max_connections` further. Each idle backend costs
memory, and 300 already sets the floor for the 4Gi limit in `postgres.yaml`.

### Health probes do not detect a Redis outage

`GET /api/v1/health` checks Redis and reports `"status": "degraded"` in the body,
but it always returns HTTP 200. Probes only look at the status code, so a pod
with unreachable Redis stays Ready. The probes here verify that the event loop is
responsive, nothing more. Alert on the response body, or on Redis directly.

`GET /api/v1/admin/health` does check Postgres and Redis properly, but it
requires a super-admin JWT and cannot be used as a probe.

### Startup seeding races across replicas

The app's lifespan hook seeds the super admin and the default template catalog on
every pod start, guarded by a `SELECT` rather than a transaction. Several
replicas starting at once can race. The inserts are idempotent enough in practice
and failures are caught and logged, so the effect is noise in the logs rather
than corruption.

### Migrations run as a Job, not an initContainer

`job-migrate.yaml` runs `alembic upgrade head` once. The app tiers each have a
`wait-for-migrations` initContainer that polls until Postgres accepts
connections and the `alembic_version` table exists, so they will not start
against an unmigrated database.

Job specs are immutable. After changing migrations, delete the old Job before
reapplying:

```bash
kubectl -n iotaps delete job iotaps-migrate --ignore-not-found
kubectl apply -k k8s/overlays/prod
kubectl -n iotaps wait --for=condition=complete job/iotaps-migrate --timeout=300s
```

`ttlSecondsAfterFinished: 3600` cleans it up automatically an hour after it
succeeds.

### Passwords must be URL-safe

`DATABASE_URL` and `REDIS_URL` are assembled inside the pod from the component
secrets using Kubernetes `$(VAR)` interpolation, so the URL can never drift from
the password the database actually uses. The tradeoff: a password containing
`@ : / ? # %` or a space corrupts the URL. Use `openssl rand -hex 24`.

To use a managed database instead, remove the assembled `DATABASE_URL` /
`REDIS_URL` entries from `api.yaml`, `ws.yaml`, `workers.yaml` and
`job-migrate.yaml`, and supply the full URLs as secret keys.

## Exposing MQTT

> **The broker performs no authentication.** `mosquitto.conf` sets
> `allow_anonymous true` and defines no topic ACLs. Devices are only
> *identified* by using their provisioning token as the MQTT client id, which
> nothing verifies. Anyone who can reach port 1883 can subscribe to every org's
> telemetry and publish commands to any device.
>
> It is also a denial-of-service vector: a single publish to
> `iotaps/x/not-a-uuid/telemetry` permanently wedges telemetry ingest for the
> whole platform. See "Application bugs surfaced while testing" below.

`base/mosquitto.yaml` only creates a ClusterIP Service, so nothing is exposed by
default. Two opt-in files add external access, and both are commented out of
their kustomizations: `overlays/prod/mosquitto-lb.yaml` (a cloud
`LoadBalancer`) and `overlays/dev/mosquitto-nodeport.yaml` (NodePort 31883, for
single-node dev clusters that have no MetalLB). A NodePort binds on *every* node
interface including public ones, and Kubernetes does not firewall it.

For occasional manual testing, prefer a port-forward — it binds to localhost only
and needs no Service at all:

```bash
kubectl -n iotaps port-forward svc/iotaps-mosquitto 1883:1883
```

Do not expose the broker without one of:

- `loadBalancerSourceRanges` restricted to known device networks (commented out
  in that file, ready to fill in), or
- a VPN / private link between devices and the cluster, or
- broker authentication: `mosquitto-go-auth` against the API, a `password_file`,
  or TLS client certificates, with `allow_anonymous false`.

MQTT is raw TCP, so it cannot go through the HTTP Ingress. The MQTT-over-
WebSocket listener on 9001 is commented out because the frontend uses the app's
own `/ws` gateway; leave it closed unless browser clients talk to the broker
directly.

Two other MQTT notes:

- **File descriptors.** Each connection costs one fd and `max_connections` is
  `-1`, so the fd limit is the real connection ceiling. The container's default
  soft limit is 1024 (measured on this image); Kubernetes has no `ulimits`
  field, so the container command raises the soft limit to 65536 in-process
  before exec'ing the broker. That only works up to the hard limit the node's
  container runtime grants. If the startup log prints the
  `could not raise nofile` warning, raise `LimitNOFILE` on the runtime.
- **Single instance.** Mosquitto 2.x does not cluster, and `mqtt_listener` holds
  one wildcard subscription, so a second broker would split the fleet.

## Security posture

Applied here:

- All application pods run as uid 1000 with `runAsNonRoot`, a read-only root
  filesystem, all capabilities dropped, and the `RuntimeDefault` seccomp
  profile. The image ships no `USER` directive, so without this it runs as root.
- Writable paths are narrow emptyDir mounts: `/tmp` (the admin
  backup-download and restore endpoints use `tempfile.mkstemp`), `/srv/backups`
  (`pg_dump` output), and `/var/run/supervisor` + `/var/log/supervisor` on the
  workers pod.
- Secrets never enter git. `k8s/overlays/*/secrets.env` is gitignored and only
  `secrets.env.example` is committed.

Not applied, and worth knowing:

- **Postgres runs as root initially.** The upstream entrypoint needs root to
  `chown` PGDATA before dropping to the `postgres` user (uid 70), so
  `runAsNonRoot` is deliberately not set on that pod.
- **NetworkPolicy is off by default.** `base/networkpolicy.yaml` has a
  default-deny plus explicit allows, but it is commented out of the
  kustomization. It is a silent no-op on CNIs that do not enforce policy, and
  some CNIs subject kubelet probes to ingress rules. Enable it deliberately and
  verify probes still pass.
- **`/srv/backups` is an emptyDir.** Dumps written by
  `POST /api/v1/admin/platform/backup` disappear when the pod restarts. It backs
  the download-a-dump workflow, not retention. Real backups belong off-cluster —
  `infra/scripts/backup-to-r2.sh` does this, but it is `docker exec`-based and
  needs rewriting as a CronJob for Kubernetes.
- **No secret encryption at rest beyond the cluster default.** For production,
  consider Sealed Secrets, External Secrets Operator, or SOPS instead of a local
  `secrets.env`.

## What is not here

- **The frontend, in `base`.** Per `DEPLOY.md` the SPA is built and hosted by
  Cloudflare Pages, so the base Ingress routes only `/api` and `/ws` and the root
  of the hostname 404s. `overlays/dev` does serve it in-cluster — see "The SPA is
  served in-cluster in dev only" above for how, and for how to promote it to
  `base` if you want the same in production.
- **Off-site backups and standby failover.** `infra/scripts/*.sh` are
  `docker exec` and Cloudflare DNS scripts tied to the single-VPS topology.
- **Observability.** No ServiceMonitor or dashboards; the app emits structured
  JSON logs to stdout and exposes no `/metrics` endpoint.

## Divergences from docker-compose.yml

| Compose | Here | Why |
|---|---|---|
| `restart: always` | default `restartPolicy: Always` | equivalent |
| `mem_limit: 1g` | `resources.limits.memory: 1Gi` | equivalent |
| `ulimits.nofile` on mosquitto | `ulimit -n` in the container command | Kubernetes has no `ulimits` field |
| nginx container terminating TLS | Ingress + cert-manager | TLS moves to the controller |
| nginx serving the SPA | not included | frontend is on Cloudflare Pages |
| `/healthz` (static nginx route) | `/api/v1/health` | `/healthz` only ever existed in nginx |
| `env_file: .env` | ConfigMap + Secret | no `.env` is baked into the image |
| supervisord.conf bind mount | ConfigMap, with control socket added | needed for the liveness probe |
| `127.0.0.1` port publishing | ClusterIP Services | not reachable outside the cluster |

## Verification

Both overlays render with Kustomize and pass `kubeconform --strict` against the
Kubernetes 1.30 schemas (dev: 20 resources, prod: 25, zero invalid).

**`overlays/dev` was then deployed to a real MicroK8s v1.36.2 cluster.** All six
workloads reached Running with zero restarts over 20 minutes, the migration Job
completed, and all three PVCs bound on `microk8s-hostpath`. Confirmed on-cluster:

- Redis runs as uid 999 / gid 1000 and Mosquitto as uid 1883, both with
  read-only root filesystems on hostpath volumes — the two things that could not
  be settled from documentation.
- The `wait-for-migrations` initContainer gated all three app tiers correctly:
  they held in `Init:0/1` until Postgres was ready and the schema was present.
- Mosquitto's `/proc/1/limits` shows 65536 open files, so the in-command
  `ulimit -n` raise works on containerd, not just Docker.
- All 11 supervisord workers Running; the liveness probe logic passes; the
  `mqtt_listener` log shows its 6 wildcard subscriptions, which is the concrete
  reason that Deployment cannot be scaled.
- MQTT publish/subscribe works both through the ClusterIP Service by DNS name and
  through `kubectl port-forward`.
- WebSockets work through MicroK8s' Traefik ingress: see the MicroK8s section
  above for the 240s idle result.

Beyond that, the container-level behaviour these manifests depend on was also
exercised locally with Docker, using the same images, the same configs, the
same non-root uids and a read-only root filesystem:

- **Postgres** starts with the tuned `-c` args through the image entrypoint, with
  `PGDATA` on a subdirectory. `pg_isready` (the probe) succeeds.
- **Redis** starts from `redis.conf` with the password appended from the
  environment; `maxmemory 512mb` and `allkeys-lru` confirmed live via
  `CONFIG GET`; the AOF is created on the mounted volume; the probe command
  returns PONG.
- **Mosquitto** starts as uid 1883 with a read-only root filesystem, both
  listeners (1883, 9001) accept connections, and a real publish/subscribe round
  trip succeeds. `/proc/1/limits` confirms the in-command `ulimit -n` raise
  reached 65536 (the container default soft limit is 1024).
- **Migration Job** applied both revisions with `workingDir: /srv/app` as uid
  1000 on a read-only filesystem, confirming `alembic/env.py` rewrites the
  `+asyncpg` URL for psycopg2.
- **Both initContainers** ran their real shell scripts to completion against a
  live database.
- **API tier** came up under the exact rendered command, served
  `GET /api/v1/health` → `200 {"status":"ok"}`, and `/api/v1/docs` plus
  `/api/v1/openapi.json` resolve under the `/api` Ingress prefix. `/srv/backups`
  and `/tmp` are writable while the root filesystem is not.
- **WS tier** came up on 8001 and serves the same health route (so the probe
  target is valid there). The ASGI route table confirms exactly one WebSocket
  route, `/ws`, at the root — which is what `ingress.yaml` targets.
- **Workers tier** ran all 11 supervisord programs as uid 1000 on a read-only
  filesystem. The liveness probe was tested in three states: all healthy → pass;
  one worker stopped → pass (`supervisorctl status` exits 3 here, which is
  exactly why the probe inspects output instead of the exit code); control socket
  removed → fail.

Three manifest bugs were found and fixed this way: `redis:7-alpine` uses gid
**1000**, not 999, so `fsGroup: 999` would have left `/data` non-writable; the
`[rpcinterface:supervisor]` factory needs a **colon** before the callable, not a
dot, or supervisord exits at startup; and the base Ingress `tls:` block made the
controller log a missing-secret error every few seconds in a cluster without
cert-manager, which `overlays/dev/patch-dev-ingress.yaml` now strips.

What is still unverified: the things only a multi-node or cloud cluster shows.
LoadBalancer provisioning (`overlays/prod/mosquitto-lb.yaml` was never applied),
HPA scaling behaviour, NetworkPolicy enforcement, real `topologySpreadConstraints`
placement, genuine ingress-nginx annotation handling, and anything about
`overlays/prod` beyond rendering.

```bash
# Re-check after editing
kubectl kustomize k8s/overlays/prod > /tmp/prod.yaml
kubeconform -strict -summary -kubernetes-version 1.30.0 /tmp/prod.yaml

# Against a live cluster
kubectl apply -k k8s/overlays/prod --dry-run=server
```

## Application bugs surfaced while testing

Neither is a Kubernetes problem; both reproduce under Compose. Recorded here
because the cluster run is what exposed them.

### A malformed telemetry message permanently wedges ingest

Publishing to `iotaps/probe/telemetry` — a topic whose device segment is not a
UUID — left the workers pod burning **880m CPU at idle**. `batch-writer` was
crash-looping 56 times, and telemetry ingest was dead for as long as it lasted.

The chain, in `app/workers/batch_writer.py`:

1. `mqtt_listener` accepts the message and `LPUSH`es it onto
   `iotaps:ingest:telemetry`.
2. `process_batch` `LRANGE`s it. `_parse_envelope` validates JSON shape but not
   that `device_id` is a UUID, so the record passes.
3. The insert fails with `asyncpg DataError: invalid UUID 'probe'`.
4. The exception propagates, so the `LTRIM` that removes the batch **never
   runs**. The bad record stays at the head of the queue.
5. supervisord restarts the worker (`autorestart=true`), it reads the same
   record, and the cycle repeats forever. Each restart re-imports FastAPI and
   SQLAlchemy, which is where the CPU goes.

`LREM`-ing the single record dropped the pod from 880m to 48m and `batch-writer`
stabilised immediately. `telemetry.device_id` has no foreign key, so a valid UUID
for a device that does not exist inserts fine — only a *malformed* device_id
poisons the queue.

Why this matters beyond a test artifact: the broker sets `allow_anonymous true`
with no topic ACLs, so anyone who can reach port 1883 can publish
`iotaps/x/not-a-uuid/telemetry` and permanently stop telemetry ingest for the
entire platform. It is a one-packet denial of service. A fix belongs in
`_parse_envelope` — reject records whose `org_id`/`device_id` are not parseable
UUIDs, and drop poison records rather than letting them block the queue head.

### Template seeding reports a false failure

```
default_templates_seed_failed  error: "Attempt to overwrite 'created' in LogRecord"
```

`app/main.py` logs `extra={"created": created}`, and `created` is a reserved
`logging.LogRecord` attribute, so the logging call raises. The templates are
seeded before that line runs and the surrounding `try/except` swallows the error,
so the effect is a misleading message rather than missing data. Renaming the key
(e.g. `templates_created`) fixes it.
