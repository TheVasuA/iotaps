import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Warning } from "@phosphor-icons/react";
import { getExpiringSubscriptions } from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ExpiringPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetchData = async () => {
    setLoading(true);
    try {
      const data = await getExpiringSubscriptions(days);
      setItems(data);
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [days]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <Warning size={20} className="text-amber-500" />
              Expiring Subscriptions
            </CardTitle>
            <CardDescription>
              Subscriptions expiring within {days} days — users will be notified.
            </CardDescription>
          </div>
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
          </select>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : items.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No subscriptions expiring within {days} days. 🎉
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-2 py-2">User</th>
                  <th className="px-2 py-2">Plan</th>
                  <th className="px-2 py-2 text-right">Days Left</th>
                  <th className="px-2 py-2">Expires</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.subscription_id} className="border-b hover:bg-muted/50">
                    <td className="px-2 py-2 font-medium">{item.email || "—"}</td>
                    <td className="px-2 py-2">
                      <Badge variant="secondary">{item.plan}</Badge>
                    </td>
                    <td className="px-2 py-2 text-right">
                      <span className={item.days_remaining <= 3 ? "font-bold text-red-600" : ""}>
                        {item.days_remaining}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-muted-foreground text-xs">
                      {new Date(item.expires_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
