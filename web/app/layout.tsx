import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { themeBootScript } from "@/components/theme";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: { default: "ProveNN — tamper-evident invoices", template: "%s · ProveNN" },
  description:
    "Fingerprint invoices when they're issued. Catch edited copies before they're reimbursed.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#efeae2" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1714" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
