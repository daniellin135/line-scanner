import type { Metadata } from "next";

import "./globals.css";


export const metadata: Metadata = {
  title: "Line Scanner",
  description: "Real-time positive expected-value betting opportunities.",
};


export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>): React.JSX.Element {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
