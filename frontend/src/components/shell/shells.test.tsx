import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render as rtlRender, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render } from "@/test/render";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/server/auth-handlers", () => ({ missingDemoVars: () => [] }));

import AppLayout from "@/app/(app)/layout";
import AppError from "@/app/(app)/error";
import NotFound from "@/app/not-found";
import LoginPage from "@/app/login/page";
import { HomePage } from "@/components/home/HomePage";

beforeEach(() => {
  vi.unstubAllEnvs();
  vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "beta@example.test");
});

// Every kind of page, as the visitor sees it. The error page is a child of the app layout (it is app/(app)/error.tsx).
const SHELLS: [string, () => ReactElement][] = [
  ["home, signed out", () => <HomePage signedIn={false} />],
  ["home, signed in (/home)", () => <HomePage signedIn />],
  ["login", () => <LoginPage />],
  ["404", () => <NotFound />],
  ["error page", () => <AppLayout><AppError error={new Error("x")} reset={() => {}} /></AppLayout>],
  ["app page", () => <AppLayout><p>content</p></AppLayout>],
];

const footerSummary = () => {
  const footer = screen.getByRole("contentinfo");
  return {
    text: footer.textContent,
    links: within(footer).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]),
  };
};

describe.each(SHELLS)("%s", (_name, ui) => {
  test("has exactly one header, one main and one footer, with the footer after main and not inside it", () => {
    render(ui());
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("contentinfo")).toHaveLength(1);
    const [header, main, footer] = [screen.getByRole("banner"), screen.getByRole("main"), screen.getByRole("contentinfo")];
    expect(main).not.toContainElement(footer);
    expect(main).not.toContainElement(header);
    expect(header.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(main.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("the header is sticky, above the composer (z-10) and opaque enough to read over content", () => {
    render(ui());
    const cls = screen.getByRole("banner").className.split(" ");
    expect(cls).toEqual(expect.arrayContaining(["sticky", "top-0", "z-20", "border-b"]));
    expect(cls.some((c) => c.startsWith("bg-surface-raised/9"))).toBe(true);
  });

  test("main is the skip link's target, the skip link comes first, and the shell is a full-height column with a growing main", () => {
    render(ui());
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "content");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(main.className).toContain("flex-1");
    expect(main.parentElement!.className).toContain("min-h-screen");
    expect(main.parentElement!.className).toContain("flex-col");
    const first = document.body.querySelector("a, button")!;
    expect(first).toHaveTextContent("Skip to content");
    expect(first).toHaveAttribute("href", "#content");
  });

  test("the header has the wordmark as a link and a theme toggle", () => {
    render(ui());
    const header = within(screen.getByRole("banner"));
    expect(header.getByRole("link", { name: "HelpHub" })).toHaveAttribute("href", expect.stringMatching(/^\/(home|documents)$/));
    expect(header.getByRole("button", { name: /theme/i })).toBeInTheDocument();
  });
});

describe("the footer is the same everywhere", () => {
  test("same text and the same links on every page", () => {
    const seen = SHELLS.map(([name, ui]) => {
      const { unmount } = render(ui());
      const summary = footerSummary();
      unmount();
      return [name, summary] as const;
    });
    const [, reference] = seen[0]!;
    expect(reference.text).toContain("Built by Krishna Keerthan K");
    expect(reference.links).toEqual([
      ["Home", "/home"],
      ["GitHub", "https://github.com/Krishna-Keerthan/HelpHub"],
      ["Contact", "mailto:beta@example.test"],
    ]);
    for (const [name, summary] of seen) expect(summary, name).toEqual(reference);
  });

  test("it follows the width rule of its page's header", () => {
    const widthOf = (el: HTMLElement) => el.className.split(" ").filter((c) => c.includes("max-w-"));
    for (const [name, ui] of SHELLS) {
      const { unmount } = render(ui());
      const header = screen.getByRole("banner").firstElementChild as HTMLElement;
      const footerBox = screen.getByRole("contentinfo").parentElement!;
      expect(widthOf(footerBox), name).toEqual(widthOf(header).filter((c) => !c.startsWith("sm:")));
      unmount();
    }
  });
});

describe("public pages", () => {
  test("login: no 'Sign in' link in the header, the form is still there", () => {
    render(<LoginPage />);
    expect(within(screen.getByRole("banner")).queryByRole("link", { name: "Sign in" })).toBeNull();
    expect(screen.queryAllByRole("link", { name: "Sign in" })).toHaveLength(0);
    expect(screen.getByRole("form", { name: "Log in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try the demo" })).toBeInTheDocument();
    // The theme toggle moved to the header: exactly one on the page.
    expect(screen.getAllByRole("button", { name: /theme/i })).toHaveLength(1);
  });

  test("404 keeps its Home and Documents links in the page body", () => {
    render(<NotFound />);
    const body = within(screen.getByRole("main"));
    expect(body.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/home");
    expect(body.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/documents");
    expect(within(screen.getByRole("banner")).queryByRole("link", { name: /sign in|open the app/i })).toBeNull();
  });

  test("the home page keeps its section links, and only the home page has them", () => {
    const home = render(<HomePage signedIn={false} />);
    const header = within(screen.getByRole("banner"));
    expect(header.getByRole("link", { name: "Features" })).toHaveAttribute("href", "#features");
    expect(header.getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "#faq");
    home.unmount();
    for (const ui of [() => <LoginPage />, () => <NotFound />]) {
      const { unmount } = render(ui());
      expect(screen.queryByRole("link", { name: "Features" })).toBeNull();
      expect(screen.queryByRole("link", { name: "FAQ" })).toBeNull();
      unmount();
    }
  });
});

describe("anchors and the skip link are not hidden under the sticky header", () => {
  test("the page leaves room at the top for every scroll-into-view, hash jump and focus scroll", () => {
    const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
    expect(css).toMatch(/html\s*{\s*scroll-padding-top:\s*7rem;\s*}/);
  });

  test("the home sections rely on that one rule instead of their own scroll-mt", () => {
    rtlRender(<HomePage signedIn={false} />);
    for (const id of ["features", "faq"]) expect(document.getElementById(id)!.className).not.toContain("scroll-mt");
  });
});
