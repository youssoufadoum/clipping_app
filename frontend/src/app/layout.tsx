import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Virello Studio — Turn long videos into scroll-stopping shorts", template: "%s · Virello Studio" },
  description:
    "Upload a long video, cut it into vertical, square or widescreen clips, and export platform-ready MP4s for TikTok, Shorts, Reels and LinkedIn.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#0a0c13",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
