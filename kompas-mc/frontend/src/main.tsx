import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { TylkoKomputer } from "./TylkoKomputer";
import "./tokeny.css";
import "./tokeny-coi.css";
import "./style.css";
import { ustawMotyw } from "./motyw";

ustawMotyw();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TylkoKomputer />
    <App />
  </StrictMode>,
);
