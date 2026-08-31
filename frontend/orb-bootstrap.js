// Bootstraps the WebGL orb and the dock/drawer chrome, then exposes the orb +
// audio tap on window so the classic app.js can drive them (setMode from the
// state machine, the waveform tap from Piper playback). Loaded as a module, so
// it runs after app.js has defined its globals.
import { initOrb } from "./orb.js?v=orb-v2";
import { attachElement, startMeter, stopMeter } from "./orb-audio.js?v=orb-v2";

const canvas = document.getElementById("orbCanvas");
const orb = canvas ? initOrb(canvas) : { setMode() {}, setAudioLevel() {} };
window.evaOrb = orb;
window.evaOrbAudio = { attachElement, startMeter, stopMeter };

// Sync the orb to whatever state the body already carries.
orb.setMode(document.body.dataset.evaState || "idle");

// ---- Dock + drawers -------------------------------------------------------
const DRAWERS = ["Chat", "Logs", "Status", "Settings"];
const scrim = document.getElementById("orbScrim");

function drawerEl(name) { return document.getElementById("drawer" + name); }
function dockBtn(name) { return document.getElementById("dock" + name); }

function closeAll() {
  DRAWERS.forEach((n) => {
    drawerEl(n)?.classList.remove("open");
    dockBtn(n)?.setAttribute("aria-expanded", "false");
  });
  scrim?.classList.remove("open");
  document.body.classList.remove("drawer-open");
}

function openDrawer(name) {
  const el = drawerEl(name);
  if (!el) return;
  const already = el.classList.contains("open");
  closeAll();
  if (already) return; // clicking the active button closes it
  el.classList.add("open");
  dockBtn(name)?.setAttribute("aria-expanded", "true");
  scrim?.classList.add("open");
  document.body.classList.add("drawer-open");
  // focus the first focusable control for keyboard users
  el.querySelector("input, select, button, textarea")?.focus?.({ preventScroll: true });
}

DRAWERS.forEach((n) => {
  dockBtn(n)?.addEventListener("click", () => openDrawer(n));
  drawerEl(n)?.querySelector(".drawer-close")?.addEventListener("click", closeAll);
});
scrim?.addEventListener("click", closeAll);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeAll();
});
