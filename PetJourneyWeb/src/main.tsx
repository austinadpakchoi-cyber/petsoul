import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/shared/theme/global.css";
import "@/shared/ui/ui.css";
import { App } from "@/app/App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
