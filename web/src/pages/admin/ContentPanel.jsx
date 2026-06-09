import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ChartLine, BellRinging } from "@phosphor-icons/react";
import {
  getSiteAnalytics,
  getNotificationSettings,
  updateNotificationSettings,
} from "@/lib/adminApi";
import { extractApiError } from "@/lib/authApi";
import useAdminData from "@/lib/useAdminData";
import AdminPanel from "@/components/admin/AdminPanel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";

// Super_Admin content panel (Task 20.7, Req 27.1, 27.3). Surfaces site analytics
// (GET /admin/site-analytics) and lets the operator toggle Telegram/push/email
// notification channels (GET/PATCH /admin/notification-settings).

function SiteAnalyticsSection() {
  const { data, status, error } = useAdminData(getSiteAnalytics);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <ChartLine size={20} className="text-primary" />
          Site analytics
        </CardTitle>
        <CardDescription>
          Page views, visitors, and sessions (Req 27.1).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AdminPanel status={status} error={error}>
          {data && Object.keys(data).length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-3">
              {Object.entries(data).map(([key, val]) => (
                <div
                  key={key}
                  className="rounded-md border border-border bg-card p-4"
                >
                  <p className="text-sm capitalize text-muted-foreground">
                    {key.replace(/_/g, " ")}
                  </p>
                  <p className="text-2xl font-semibold text-foreground">
                    {typeof val === "object" ? JSON.stringify(val) : String(val)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No analytics data.</p>
          )}
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

function channelEnabled(channel) {
  return Boolean(channel && (channel.enabled ?? false));
}

function NotificationSettingsSection() {
  const { data, status, error } = useAdminData(getNotificationSettings);
  const [settings, setSettings] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data) setSettings(data);
  }, [data]);

  const toggle = (channel) => {
    setSettings((prev) => ({
      ...prev,
      [channel]: { ...(prev[channel] || {}), enabled: !channelEnabled(prev[channel]) },
    }));
  };

  const onSave = async () => {
    setBusy(true);
    try {
      const updated = await updateNotificationSettings({
        telegram: settings.telegram,
        push: settings.push,
        email: settings.email,
      });
      setSettings(updated);
      toast.success("Notification settings saved");
    } catch (err) {
      toast.error(extractApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const channels = [
    { key: "telegram", label: "Telegram" },
    { key: "push", label: "Push" },
    { key: "email", label: "Email" },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <BellRinging size={20} className="text-primary" />
          Notification settings
        </CardTitle>
        <CardDescription>
          Toggle platform-wide notification channels (Req 27.3).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <AdminPanel status={status} error={error}>
          <div className="space-y-3">
            {channels.map(({ key, label }) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-md border border-border bg-card px-4 py-3"
              >
                <span className="text-sm text-foreground">{label}</span>
                <Switch
                  checked={channelEnabled(settings[key])}
                  onChange={() => toggle(key)}
                  aria-label={`Toggle ${label} notifications`}
                />
              </div>
            ))}
            <Button type="button" onClick={onSave} disabled={busy}>
              Save settings
            </Button>
          </div>
        </AdminPanel>
      </CardContent>
    </Card>
  );
}

export default function ContentPanel() {
  return (
    <section className="space-y-6">
      <SiteAnalyticsSection />
      <NotificationSettingsSection />
    </section>
  );
}
