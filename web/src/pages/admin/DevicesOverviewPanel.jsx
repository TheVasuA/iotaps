import { useEffect, useState } from "react";
import { toast } from "sonner";
import { WifiHigh, WifiSlash } from "@phosphor-icons/react";
import { getAdminDevices } from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export default function DevicesOverviewPanel() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    (async () => {
      try {
        const data = await getAdminDevices();
        setDevices(data);
      } catch (err) {
        toast.error(extractApiError(err).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = devices.filter((d) => {
    if (statusFilter !== "all" && d.status !== statusFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        (d.label || "").toLowerCase().includes(q) ||
        (d.device_uid || "").toLowerCase().includes(q) ||
        (d.owner_email || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const onlineCount = devices.filter((d) => d.status === "online").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">All Devices</CardTitle>
        <CardDescription>
          {devices.length} total • {onlineCount} online • {devices.length - onlineCount} offline
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Input
            placeholder="Search by label, UID, or owner..."
            className="max-w-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
          </select>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : filtered.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No devices found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-2 py-2">Device</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Owner</th>
                  <th className="px-2 py-2 text-right">Subscription</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => {
                  const expiring = d.subscription_days_remaining !== null && d.subscription_days_remaining < 7;
                  return (
                    <tr key={d.id} className="border-b hover:bg-muted/50">
                      <td className="px-2 py-2">
                        <div className="font-medium">{d.label || d.device_uid || "Unnamed"}</div>
                        {d.device_uid && d.label && (
                          <div className="text-xs text-muted-foreground">{d.device_uid}</div>
                        )}
                      </td>
                      <td className="px-2 py-2">
                        <Badge variant={d.status === "online" ? "success" : "muted"}>
                          {d.status === "online" ? <WifiHigh size={12} className="mr-1" /> : <WifiSlash size={12} className="mr-1" />}
                          {d.status}
                        </Badge>
                      </td>
                      <td className="px-2 py-2 text-muted-foreground">{d.owner_email || "—"}</td>
                      <td className="px-2 py-2 text-right">
                        {d.subscription_days_remaining !== null ? (
                          <span>
                            {d.subscription_days_remaining}d
                            {expiring && <Badge className="ml-1 bg-red-500/15 text-red-600">Expiring</Badge>}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Free</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
