import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Dashboard } from "../app/dashboard";
import "../app/globals.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("PulseOps root element was not found");
}

createRoot(root).render(
  <StrictMode>
    <Dashboard />
  </StrictMode>,
);
