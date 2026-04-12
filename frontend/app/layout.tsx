import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tax Brain — CPA Platform",
  description: "CPA tax preparation platform powered by AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-screen overflow-hidden flex flex-col">{children}</body>
    </html>
  );
}
