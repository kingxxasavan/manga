import type { Metadata, Viewport } from "next";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";
import { KEYS } from "@/lib/storage";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${SITE_NAME}: read manga, manhwa and manhua`, template: `%s | ${SITE_NAME}` },
  description: SITE_TAGLINE,
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0c0d11" },
    { media: "(prefers-color-scheme: light)", color: "#faf6f0" },
  ],
};

// Runs before first paint so the saved (or system) theme never flashes.
const themeScript = `try{var t=JSON.parse(localStorage.getItem(${JSON.stringify(KEYS.theme)}));if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="dark"}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
