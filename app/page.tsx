import type { Metadata } from "next";
import { Dashboard } from "./dashboard";

export const metadata: Metadata = {
  title: "PulseOps — Observabilidad simple, incidentes claros",
  description:
    "Monitorea tus servicios, detecta caídas y entiende cada incidente desde un solo lugar.",
};

export default function Home() {
  return <Dashboard />;
}
