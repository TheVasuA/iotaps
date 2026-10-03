// Pure helpers for the public contact form.
//
// There is no public contact endpoint (and no mail transport server-side), so
// submitting the form prepares a mailto: URL the visitor opens in their own
// mail client. Keeping this logic DOM-free means vitest can cover it without a
// browser environment.

export const CONTACT_EMAIL = "support@iotaps.com";

/** Messages shorter than this are almost always "hi" with nothing to act on. */
export const MESSAGE_MIN_LENGTH = 20;

// Pragmatic shape check, not RFC 5322: a stricter pattern mostly rejects
// valid-but-unusual addresses on a form whose only job is filling a mailto URL.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Validate the contact form fields.
 *
 * Returns an object with one entry per invalid field (empty object when the
 * form is valid). Values are trimmed before checking, so whitespace alone does
 * not count as content.
 */
export function validateContactForm(values) {
  const errors = {};
  const name = (values?.name ?? "").trim();
  const email = (values?.email ?? "").trim();
  const subject = (values?.subject ?? "").trim();
  const message = (values?.message ?? "").trim();

  if (!name) {
    errors.name = "Please enter your name.";
  }
  if (!email) {
    errors.email = "Please enter your email address.";
  } else if (!EMAIL_RE.test(email)) {
    errors.email = "Please enter a valid email address.";
  }
  if (!subject) {
    errors.subject = "Please enter a subject.";
  }
  if (!message) {
    errors.message = "Please enter a message.";
  } else if (message.length < MESSAGE_MIN_LENGTH) {
    errors.message = `Message must be at least ${MESSAGE_MIN_LENGTH} characters.`;
  }

  return errors;
}

/**
 * Build the mailto: URL for the support inbox, with the visitor's name and
 * email in the body so the reply address is visible even when the mail client
 * rewrites the From header.
 */
export function buildContactMailto(values) {
  const name = (values?.name ?? "").trim();
  const email = (values?.email ?? "").trim();
  const subject = (values?.subject ?? "").trim();
  const message = (values?.message ?? "").trim();

  const body = [`Name: ${name}`, `Email: ${email}`, "", message].join("\n");
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/**
 * Plain-text rendering of the message details, for the clipboard fallback used
 * by visitors without a configured mail client.
 */
export function formatContactDetails(values) {
  const name = (values?.name ?? "").trim();
  const email = (values?.email ?? "").trim();
  const subject = (values?.subject ?? "").trim();
  const message = (values?.message ?? "").trim();

  return [`To: ${CONTACT_EMAIL}`, `Subject: ${subject}`, `Name: ${name}`, `Email: ${email}`, "", message].join("\n");
}
