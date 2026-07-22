import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const imageUrl = `${protocol}://${host}/og.png`;
  return {
    title: { default: "PulseOps", template: "%s · PulseOps" },
    description: "Monitoreo de servicios e incidentes en tiempo real.",
    openGraph: {
      title: "PulseOps",
      description: "Observabilidad simple. Incidentes claros.",
      type: "website",
      locale: "es_CL",
      images: [{ url: imageUrl, width: 1536, height: 1024, alt: "Dashboard de observabilidad PulseOps" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "PulseOps",
      description: "Observabilidad simple. Incidentes claros.",
      images: [imageUrl],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body></html>;
}
