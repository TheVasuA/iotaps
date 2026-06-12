import { useEffect, useState, useCallback } from "react";
import {
  HardDrive,
  Memory,
  Cpu,
  WifiHigh,
  Database,
  Queue,
} from "@phosphor-icons/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import wsManager from "@/lib/websocket";
import { getSystemStats } from "@/lib/adminApi";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function ProgressBar({ percent, color = "bg-primary" }) {
  const barColor =
    percent > 90 ? "bg-destructive" : percent > 70 ? "bg-yellow-500" : color;
  return (
    <div className="h-3 w-full overflow-hidden rounded-full bg-secondary">
      <div
        className={`h-full rounded-full transition-all duration-500 ${barColor}`}
        style={{ width: `${Math.min(percent, 100)}%` }}
      />
    </div>
  );
}

function StatCard({ icon: Icon, title, value, subtitle, percent }) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon size={20} className="text-primary" />
            <span className="text-sm font-medium text-foreground">{title}</span>
          </div>
          <span className="text-lg font-bold text-foreground">{value}</span>
        </div>
        {percent != null && <ProgressBar percent={percent} />}
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function SystemStatsPanel() {
  const [stats, setStats] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Subscribe to admin:stats WebSocket channel for live updates
  useEffect(() => {
    wsManager.connect();
    wsManager.subscribe(["admin:stats"]);

    const offStatus = wsManager.onStatus((status) => {
      setWsConnected(status === "open");
    });

    const offMessage = wsManager.onMessage((msg) => {
      if (msg.type === "system_stats") {
        setStats(msg);
      }
    });

    return () => {
      offStatus();
      offMessage();
      wsManager.unsubscribe(["admin:stats"]);
    };
  }, []);

  // Fallback: fetch via REST API on mount and every 10s if WS not connected
  const fetchStats = useCallback(async () => {
    try {
      const data = await getSystemStats();
      setStats(data);
    } catch {
      // silently fail - WS will provide data
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(() => {
      if (!wsConnected) fetchStats();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchStats, wsConnected]);

  if (!stats) {
    return (
      <div className="flex items-center justify-center p-12 text-muted-foreground">
        Loading system stats...
      </div>
    );
  }

  const ram = stats.ram || {};
  const disk = stats.disk || {};
  const redisMemory = stats.redis_memory || {};

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            System Resources
          </h2>
          <p className="text-sm text-muted-foreground">
            Live server metrics — designed for 10K max device connections
          </p>
        </div>
        <Badge variant={wsConnected ? "success" : "muted"}>
          {wsConnected ? "● Live" : "○ Polling"}
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          icon={Memory}
          title="RAM"
          value={`${ram.percent || 0}%`}
          percent={ram.percent}
          subtitle={`${formatBytes(ram.used_bytes)} / ${formatBytes(ram.total_bytes)}`}
        />
        <StatCard
          icon={HardDrive}
          title="Disk"
          value={`${disk.percent || 0}%`}
          percent={disk.percent}
          subtitle={`${formatBytes(disk.used_bytes)} / ${formatBytes(disk.total_bytes)}`}
        />
        <StatCard
          icon={Cpu}
          title="CPU"
          value={`${stats.cpu_percent || 0}%`}
          percent={stats.cpu_percent}
          subtitle="Average across all cores"
        />
        <StatCard
          icon={WifiHigh}
          title="MQTT Connections"
          value={`${stats.mqtt_connections || 0}`}
          percent={((stats.mqtt_connections || 0) / (stats.max_connections_design || 10000)) * 100}
          subtitle={`Capacity: ${stats.max_connections_design || 10000} devices`}
        />
        <StatCard
          icon={Database}
          title="Redis Memory"
          value={formatBytes(redisMemory.used_bytes)}
          subtitle={`Peak: ${formatBytes(redisMemory.peak_bytes)}`}
        />
        <StatCard
          icon={Queue}
          title="Ingest Queue"
          value={`${stats.ingest_queue_size || 0}`}
          percent={Math.min(((stats.ingest_queue_size || 0) / 10000) * 100, 100)}
          subtitle="Pending telemetry messages"
        />
      </div>
    </section>
  );
}
