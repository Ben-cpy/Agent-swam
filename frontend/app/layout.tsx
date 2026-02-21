import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import ToBeReviewNotifier from "@/components/ToBeReviewNotifier";

export const metadata: Metadata = {
  title: "Agent Swarm",
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
        <ToBeReviewNotifier />
        <Navbar />
        <main className="container mx-auto px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
