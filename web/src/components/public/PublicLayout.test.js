// Pure-function tests for the public-header nav matcher. No jsdom: the header
// itself is a component and cannot be rendered under this Vitest setup, so
// these pin the pathname rules that decide which item lights up.

import { describe, it, expect } from "vitest";
import { isNavActive } from "./PublicLayout.jsx";

// Mirrors the header's own shape: `to` is the mounted path, `matchPrefix` is
// the alternate URL space the same item must also claim.
const developers = { to: "/docs", label: "Developers", matchPrefix: "/developers" };
const platform = { to: "/platform", label: "Platform", matchPrefix: "/platform" };
const about = { to: "/about", label: "About" };

describe("isNavActive", () => {
  it("lights up on the mounted path", () => {
    expect(isNavActive(developers, "/docs")).toBe(true);
    expect(isNavActive(platform, "/platform")).toBe(true);
    expect(isNavActive(about, "/about")).toBe(true);
  });

  it("lights up on nested routes under either base", () => {
    expect(isNavActive(developers, "/docs/getting-started")).toBe(true);
    expect(isNavActive(developers, "/developers")).toBe(true);
    expect(isNavActive(developers, "/developers/mqtt-devices")).toBe(true);
    expect(isNavActive(developers, "/developers/dashboards-api")).toBe(true);
    expect(isNavActive(platform, "/platform/automation")).toBe(true);
  });

  it("does not light up on sibling routes", () => {
    expect(isNavActive(developers, "/pricing")).toBe(false);
    expect(isNavActive(developers, "/documentation")).toBe(false);
    expect(isNavActive(platform, "/platforms")).toBe(false);
    expect(isNavActive(about, "/about-us")).toBe(false);
    expect(isNavActive(about, "/")).toBe(false);
  });

  it("treats a bare item as exact-plus-children with no extra base", () => {
    expect(isNavActive(about, "/about")).toBe(true);
    expect(isNavActive(about, "/about/team")).toBe(true);
    expect(isNavActive(about, "/abouts")).toBe(false);
  });
});
