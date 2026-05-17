import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Meridian Capital Partners — JARVIS",
  description: "Long/Short Equity Hedge Fund Intelligence System",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" style={{ background: "#0b0e17" }}>
      <body style={{ minHeight: "100vh", background: "#0b0e17" }}>
        <NavBar />
        <main style={{ padding: "24px 32px", maxWidth: 1600, margin: "0 auto" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
