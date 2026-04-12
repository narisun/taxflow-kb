import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "./providers";

export const metadata: Metadata = {
  title: "TaxFlow AI — CPA Platform",
  description: "AI-powered tax preparation platform for CPAs",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-screen overflow-hidden flex flex-col" suppressHydrationWarning>
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
