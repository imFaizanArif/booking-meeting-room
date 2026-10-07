import "./globals.css";

import type { Metadata } from "next";

import { themeBootScript } from "@/stores/ui";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Agent Platform", template: "%s · Agent Platform" },
  description: "Control plane for autonomous agent pipelines",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
