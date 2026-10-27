import type { ReactElement } from "react";
import { beforeEach, expect, test, vi } from "vitest";

const jar = vi.hoisted(() => ({ value: undefined as string | undefined }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => (name === "hh_theme" && jar.value !== undefined ? { name, value: jar.value } : undefined) }),
}));
vi.mock("next/font/google", () => ({ Inter: () => ({ variable: "inter-var" }) }));
vi.mock("./globals.css", () => ({}));

import RootLayout from "./layout";

beforeEach(() => {
  jar.value = undefined;
});

/** The layout is a server component returning <html>; read its props instead of mounting <html> in a div. */
async function htmlProps(): Promise<Record<string, unknown>> {
  const el = (await RootLayout({ children: null })) as ReactElement<Record<string, unknown>>;
  return el.props;
}

test.each(["light", "dark"])("a valid %s cookie renders data-theme on <html>", async (value) => {
  jar.value = value;
  expect((await htmlProps())["data-theme"]).toBe(value);
});

test.each([undefined, "", "auto", "Dark", "dark; x=1"])("cookie %j sets no data-theme (the OS decides)", async (value) => {
  jar.value = value;
  expect((await htmlProps())["data-theme"]).toBeUndefined();
});

test("the rest of <html> is unchanged: lang and the font variable class", async () => {
  const props = await htmlProps();
  expect(props.lang).toBe("en");
  expect(props.className).toBe("inter-var");
});
