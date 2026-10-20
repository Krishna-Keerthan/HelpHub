import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HelpHub",
  description: "Support knowledge engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-zinc-900">{children}</body>
    </html>
  );
}
