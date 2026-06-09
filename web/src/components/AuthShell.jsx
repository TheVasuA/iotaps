import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import ThemeModeToggle from "@/components/ThemeModeToggle";

// Shared frame for the unauthenticated auth screens (login, register, 2FA,
// password reset). Keeps the role/mode theme tokens visible so the toggle and
// palette behave the same as the rest of the app (Req 4.x).
export default function AuthShell({ title, description, children, footer }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
      <div className="absolute right-4 top-4">
        <ThemeModeToggle />
      </div>
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <span className="text-2xl font-bold text-primary">IoTAPS</span>
          <p className="text-xs text-muted-foreground">IoT Automation Platform Services</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{title}</CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </CardHeader>
          <CardContent className="space-y-4">{children}</CardContent>
        </Card>
        {footer ? (
          <p className="text-center text-sm text-muted-foreground">{footer}</p>
        ) : null}
      </div>
    </div>
  );
}
