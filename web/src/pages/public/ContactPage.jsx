import { useState } from "react";
import {
  Envelope,
  ChatCircleText,
  MapPin,
  Copy,
  Check,
  PaperPlaneTilt,
} from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { MarketingShell } from "@/components/public/PublicPage";
import { marketingImages } from "@/lib/marketingImages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  CONTACT_EMAIL,
  MESSAGE_MIN_LENGTH,
  buildContactMailto,
  formatContactDetails,
  validateContactForm,
} from "@/lib/contactForm";

const channels = [
  {
    icon: Envelope,
    title: "Email",
    description: "Reach our team for sales and general questions.",
    display: CONTACT_EMAIL,
    href: `mailto:${CONTACT_EMAIL}`,
  },
  {
    icon: ChatCircleText,
    title: "In-app support",
    description: "Signed-in users can chat with their project center directly.",
    display: "Open the app",
    href: "/login",
  },
  {
    icon: MapPin,
    title: "Office",
    description: "We operate remotely across India.",
    display: "India",
    href: null,
  },
];

const emptyForm = { name: "", email: "", subject: "", message: "" };

const fieldLabels = {
  name: "Name",
  email: "Email",
  subject: "Subject",
  message: "Message",
};

function ContactForm() {
  const [values, setValues] = useState(emptyForm);
  const [errors, setErrors] = useState({});
  const [prepared, setPrepared] = useState(false);
  const [copyState, setCopyState] = useState("idle"); // idle | copied | manual

  const setField = (field) => (event) => {
    const value = event.target.value;
    setValues((prev) => ({ ...prev, [field]: value }));
    // Clear the error as soon as the visitor starts fixing the field.
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const onSubmit = (event) => {
    event.preventDefault();
    const nextErrors = validateContactForm(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setPrepared(false);
      return;
    }
    // No backend endpoint exists for public contact mail, so the submit hands
    // a prepared message to the visitor's own mail client. Nothing is sent
    // server-side and the copy below must keep saying so.
    window.location.href = buildContactMailto(values);
    setPrepared(true);
  };

  const copyDetails = async () => {
    const text = formatContactDetails(values);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(text);
      setCopyState("copied");
    } catch {
      // Clipboard access can be blocked (insecure context, permissions) —
      // fall back to showing the details so they can be copied by hand.
      setCopyState("manual");
    }
  };

  const errorEntries = Object.entries(errors);

  return (
    <form onSubmit={onSubmit} noValidate className="blynk-platform-card p-6 sm:p-8">
      {/* h2: sits directly under the page hero's h1, so h3 would skip a level. */}
      <h2 className="text-lg font-bold uppercase tracking-wide">Send us a message</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Fill this in and we'll open a prepared draft in your mail client — review it there
        and press send. Nothing is sent automatically.
      </p>

      {/* Always mounted so the live region exists before errors appear. */}
      <div role="alert" aria-live="assertive" className={errorEntries.length > 0 ? "mt-4" : ""}>
        {errorEntries.length > 0 ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <p className="font-semibold">
              Please fix {errorEntries.length === 1 ? "the field" : "the fields"} below.
            </p>
            <ul className="mt-1 list-inside list-disc">
              {errorEntries.map(([field, message]) => (
                <li key={field}>
                  {fieldLabels[field]}: {message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="contact-name">Name</Label>
          <Input
            id="contact-name"
            name="name"
            value={values.name}
            onChange={setField("name")}
            autoComplete="name"
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "contact-name-error" : undefined}
            required
          />
          {errors.name ? (
            <p id="contact-name-error" className="text-sm text-destructive">
              {errors.name}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          <Label htmlFor="contact-email">Email</Label>
          <Input
            id="contact-email"
            name="email"
            type="email"
            value={values.email}
            onChange={setField("email")}
            autoComplete="email"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "contact-email-error" : undefined}
            required
          />
          {errors.email ? (
            <p id="contact-email-error" className="text-sm text-destructive">
              {errors.email}
            </p>
          ) : null}
        </div>

        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="contact-subject">Subject</Label>
          <Input
            id="contact-subject"
            name="subject"
            value={values.subject}
            onChange={setField("subject")}
            autoComplete="off"
            aria-invalid={Boolean(errors.subject)}
            aria-describedby={errors.subject ? "contact-subject-error" : undefined}
            required
          />
          {errors.subject ? (
            <p id="contact-subject-error" className="text-sm text-destructive">
              {errors.subject}
            </p>
          ) : null}
        </div>

        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="contact-message">Message</Label>
          <textarea
            id="contact-message"
            name="message"
            rows={6}
            value={values.message}
            onChange={setField("message")}
            autoComplete="off"
            aria-invalid={Boolean(errors.message)}
            aria-describedby={
              errors.message ? "contact-message-hint contact-message-error" : "contact-message-hint"
            }
            required
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <p id="contact-message-hint" className="text-sm text-muted-foreground">
            At least {MESSAGE_MIN_LENGTH} characters — enough for us to act on.
          </p>
          {errors.message ? (
            <p id="contact-message-error" className="text-sm text-destructive">
              {errors.message}
            </p>
          ) : null}
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button type="submit">
          <PaperPlaneTilt size={16} weight="bold" />
          Open draft in mail app
        </Button>
        <p className="text-sm text-muted-foreground">
          Opens your mail client — this site can't send the message for you.
        </p>
      </div>

      {prepared ? (
        <div className="mt-6 rounded-md border border-border bg-muted/30 px-4 py-4 text-sm">
          <p className="font-semibold text-foreground">
            Your mail app should now have a prepared message.
          </p>
          <p className="mt-2 text-muted-foreground">
            Nothing has been sent yet — review the draft in your mail app and press send
            there. If no mail app opened, write to us directly at{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="font-semibold text-sky-600 hover:underline"
            >
              {CONTACT_EMAIL}
            </a>{" "}
            or copy the details below into any mail or webmail client.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={copyDetails}>
              {copyState === "copied" ? <Check size={16} weight="bold" /> : <Copy size={16} />}
              {copyState === "copied" ? "Copied" : "Copy details to clipboard"}
            </Button>
            <span role="status" aria-live="polite" className="text-muted-foreground">
              {copyState === "copied" ? "Message details copied to your clipboard." : ""}
            </span>
          </div>
          {copyState === "manual" ? (
            <div className="mt-3">
              <p className="text-muted-foreground">
                Clipboard access is unavailable in this browser. Select the text below and
                copy it manually.
              </p>
              <textarea
                readOnly
                rows={6}
                value={formatContactDetails(values)}
                aria-label="Message details to copy manually"
                onFocus={(event) => event.target.select()}
                className="mt-2 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

export default function ContactPage() {
  return (
    <MarketingShell
      eyebrow="Contact"
      title="Contact us"
      subtitle="We'd love to hear from you. Pick the channel that suits you best."
      image={marketingImages.consoleDesk}
      imageAlt="Workspace with IoT dashboard on laptop"
      imagePosition="left"
    >
      <ContactForm />

      <div className="mt-10">
        {/* h2: keeps heading order under the hero h1 alongside the form title. */}
        <h2 className="text-lg font-bold uppercase tracking-wide">Other ways to reach us</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {channels.map((channel) => {
            const Icon = channel.icon;
            return (
              <article key={channel.title} className="blynk-platform-card p-6">
                <Icon size={28} className="text-primary" weight="duotone" />
                {/* h3: cards sit under the section's h2, not the hero's h1. */}
                <h3 className="mt-4 text-base font-bold uppercase tracking-wide">{channel.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{channel.description}</p>
                <div className="mt-4">
                  {channel.href ? (
                    channel.href.startsWith("/") ? (
                      <Link to={channel.href} className="text-sm font-semibold text-sky-600 hover:underline">
                        {channel.display}
                      </Link>
                    ) : (
                      <a href={channel.href} className="text-sm font-semibold text-sky-600 hover:underline">
                        {channel.display}
                      </a>
                    )
                  ) : (
                    <span className="text-sm font-semibold text-foreground">{channel.display}</span>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </MarketingShell>
  );
}
