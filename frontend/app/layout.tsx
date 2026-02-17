import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import QuotaAlert from "@/components/QuotaAlert";

export const metadata: Metadata = {
  title: "AI Task Manager",
  description: "Manage AI tasks with Claude Code and Codex CLI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Navbar />
        <QuotaAlert />
        <main className="container mx-auto px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
