import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { notFound } from "next/navigation";
import { NavTracker } from "@/components/BackLink";
import { isLocale, locales } from "@/i18n/config";
import "../globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin"], weight: ["500", "600", "700"] });

export const metadata: Metadata = {
  title: { default: "pyRasca", template: "%s · pyRasca" },
  description: "Compare ONCE scratch cards: return per €1, odds, claimed top prizes and end dates.",
};

export function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  return (
    <html lang={lang} className={`${inter.variable} ${spaceGrotesk.variable} antialiased`}>
      <body className="min-h-screen font-sans">
        <NavTracker />
        {children}
      </body>
    </html>
  );
}
