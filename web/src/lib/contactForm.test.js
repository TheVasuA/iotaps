// Unit tests for the contact form's pure helpers (Task: real contact form).
// The page has no backend to post to, so the mailto builder and validators are
// the whole submission contract — exercised here without a DOM.

import { describe, it, expect } from "vitest";
import {
  CONTACT_EMAIL,
  MESSAGE_MIN_LENGTH,
  validateContactForm,
  buildContactMailto,
  formatContactDetails,
} from "./contactForm.js";

const validForm = {
  name: "Ada Lovelace",
  email: "ada@example.com",
  subject: "Sensor integration",
  message: "We would like to discuss connecting our warehouse sensors.",
};

describe("validateContactForm", () => {
  it("accepts a well-formed submission", () => {
    expect(validateContactForm(validForm)).toEqual({});
  });

  it("flags every empty field", () => {
    expect(validateContactForm({})).toEqual({
      name: expect.any(String),
      email: expect.any(String),
      subject: expect.any(String),
      message: expect.any(String),
    });
  });

  it("treats whitespace-only values as empty", () => {
    const errors = validateContactForm({
      name: "   ",
      email: " ",
      subject: "\t",
      message: "  \n ",
    });
    expect(Object.keys(errors).sort()).toEqual(["email", "message", "name", "subject"]);
  });

  it("rejects malformed email addresses", () => {
    for (const email of ["ada", "ada@", "@example.com", "ada@example", "a b@example.com"]) {
      expect(validateContactForm({ ...validForm, email }).email).toBeTruthy();
    }
  });

  it("rejects a message shorter than the minimum", () => {
    const short = "x".repeat(MESSAGE_MIN_LENGTH - 1);
    const errors = validateContactForm({ ...validForm, message: short });
    expect(errors.message).toContain(String(MESSAGE_MIN_LENGTH));
  });

  it("accepts a message exactly at the minimum length", () => {
    const exact = "x".repeat(MESSAGE_MIN_LENGTH);
    expect(validateContactForm({ ...validForm, message: exact })).toEqual({});
  });

  it("ignores surrounding whitespace when measuring the message", () => {
    const padded = `  ${"x".repeat(MESSAGE_MIN_LENGTH)}  `;
    expect(validateContactForm({ ...validForm, message: padded })).toEqual({});
  });

  it("reports only the offending fields", () => {
    const errors = validateContactForm({ ...validForm, email: "not-an-email" });
    expect(Object.keys(errors)).toEqual(["email"]);
  });
});

describe("buildContactMailto", () => {
  it("addresses the support inbox", () => {
    const mailto = buildContactMailto(validForm);
    expect(mailto.startsWith(`mailto:${CONTACT_EMAIL}?`)).toBe(true);
  });

  it("URL-encodes subject and body", () => {
    const values = {
      name: "A & B",
      email: "a+b@example.com",
      subject: "Q1? 50% off",
      message: "Line one\nLine two & three",
    };
    const mailto = buildContactMailto(values);
    const [, query] = mailto.split("?");
    const params = new URLSearchParams(query);

    expect(params.get("subject")).toBe(values.subject);
    expect(params.get("body")).toContain(values.message);
    expect(params.get("body")).toContain(values.name);
    expect(params.get("body")).toContain(values.email);
    // Raw newlines must not leak into the URL itself.
    expect(mailto).not.toContain("\n");
  });

  it("omits nothing when values are missing", () => {
    const mailto = buildContactMailto({});
    expect(mailto).toContain(`mailto:${CONTACT_EMAIL}`);
    expect(mailto).toContain("body=");
  });
});

describe("formatContactDetails", () => {
  it("renders a copyable plain-text block", () => {
    const text = formatContactDetails(validForm);
    expect(text).toContain(`To: ${CONTACT_EMAIL}`);
    expect(text).toContain(`Subject: ${validForm.subject}`);
    expect(text).toContain(`Name: ${validForm.name}`);
    expect(text).toContain(`Email: ${validForm.email}`);
    expect(text).toContain(validForm.message);
  });

  it("tolerates missing fields without throwing", () => {
    expect(() => formatContactDetails({})).not.toThrow();
  });
});
