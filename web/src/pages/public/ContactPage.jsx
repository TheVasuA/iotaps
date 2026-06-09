import { Envelope, ChatCircleText, MapPin } from "@phosphor-icons/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { PublicPage, PageHeader } from "@/components/public/PublicPage";

// Public Contact page (Task 21.1, Req 31.1). Static contact information; the
// authenticated app provides live support chat (Req 21) for signed-in users.

const channels = [
  {
    icon: Envelope,
    title: "Email",
    description: "Reach our team for sales and general questions.",
    value: "support@iotaps.in",
    href: "mailto:support@iotaps.in",
  },
  {
    icon: ChatCircleText,
    title: "In-app support",
    description: "Signed-in users can chat with their project center directly.",
    value: "Open the app",
    href: "/login",
  },
  {
    icon: MapPin,
    title: "Office",
    description: "We operate remotely across India.",
    value: "India",
    href: null,
  },
];

export default function ContactPage() {
  return (
    <PublicPage>
      <PageHeader
        title="Contact us"
        subtitle="We'd love to hear from you. Pick the channel that suits you best."
      />
      <div className="grid gap-6 sm:grid-cols-3">
        {channels.map((channel) => {
          const Icon = channel.icon;
          return (
            <Card key={channel.title}>
              <CardHeader>
                <Icon size={26} className="text-primary" weight="duotone" />
                <CardTitle className="text-lg">{channel.title}</CardTitle>
                <CardDescription>{channel.description}</CardDescription>
              </CardHeader>
              <CardContent>
                {channel.href ? (
                  <a
                    href={channel.href}
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    {channel.value}
                  </a>
                ) : (
                  <span className="text-sm font-medium text-foreground">
                    {channel.value}
                  </span>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </PublicPage>
  );
}
