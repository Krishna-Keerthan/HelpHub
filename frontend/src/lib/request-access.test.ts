import { expect, test } from "vitest";
import { ACCESS_SUBJECT, requestAccessHref } from "./request-access";

test("mailto has the encoded subject and the three fields", () => {
  const href = requestAccessHref("beta@example.test")!;
  expect(href.startsWith("mailto:beta@example.test?")).toBe(true);
  const q = new URL(href.replace("mailto:", "http://x/")).searchParams;
  expect(href).toContain("subject=HelpHub%20access%20request");
  expect(q.get("subject")).toBe(ACCESS_SUBJECT);
  const body = q.get("body")!;
  expect(body).toContain("Workspace name:");
  expect(body).toContain("Workspace slug (lowercase letters, digits, hyphens):");
  expect(body).toContain("Admin email:");
});

test("the body says never to send a password and has no password field", () => {
  const body = new URL(requestAccessHref("a@b.test")!.replace("mailto:", "http://x/")).searchParams.get("body")!;
  expect(body).toMatch(/Never send a password/);
  expect(body.replace(/Never send a password/, "")).not.toMatch(/password/i);
});

test.each([undefined, "", "   "])("missing contact %j gives no link", (v) => {
  expect(requestAccessHref(v)).toBeNull();
});
