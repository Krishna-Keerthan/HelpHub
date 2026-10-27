import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { cookies } from "next/headers";
import { Providers } from "@/components/Providers";
import { parseTheme, THEME_COOKIE } from "@/lib/theme";
import "./globals.css";

// The system stack in globals.css (--font-sans) is the fallback if the font file is unavailable.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "HelpHub",
  description: "Support knowledge engine",
};

// Reading cookies() makes every route dynamic (D16). No cookie, or a value other than light/dark, sets no
// data-theme, so the OS preference applies.
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const theme = parseTheme((await cookies()).get(THEME_COOKIE)?.value);
  return (
    <html lang="en" className={inter.variable} data-theme={theme}>
      <body className="min-h-screen bg-surface font-sans text-fg antialiased"><Providers>{children}</Providers></body>
    </html>
  );
}
