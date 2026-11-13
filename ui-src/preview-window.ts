// The separate preview window (design document F7.2, built in M5): the pages
// of the active adventure, with the same zoom bar as the preview pane. It
// talks to the same core over Qt WebChannel and follows every build.

import { call, connect, on } from "./bridge";
import { applyStrings, setStrings } from "./i18n";
import { applyZoom, initZoom, loadZoom } from "./preview";

const $ = (id: string) => document.getElementById(id) as HTMLElement;

function show(result: any): void {
  if (!result) return;
  const banner = $("preview-error");
  if (!result.ok) {
    // F7.1.2: the last good pages stay.
    banner.textContent = (result.errors ?? []).map((e: any) => e.text).join("\n");
    banner.classList.remove("hidden");
    return;
  }
  banner.classList.add("hidden");
  const box = $("pages");
  const imgs = box.querySelectorAll("img");
  (result.pages as string[]).forEach((url, i) => {
    let img = imgs[i] as HTMLImageElement | undefined;
    if (!img) {
      img = document.createElement("img");
      img.className = "page";
      img.addEventListener("load", () => applyZoom());
      box.append(img);
    }
    img.src = url;
  });
  for (let i = result.pages.length; i < imgs.length; i++) imgs[i].remove();
  applyZoom();
  document.body.dataset.buildCount = String(Number(document.body.dataset.buildCount || 0) + 1);
}

async function boot(): Promise<void> {
  await connect();
  setStrings(await call("strings"));
  applyStrings(document);
  document.title = (await call("previewWindowTitle")).title;
  // F16: the window takes the palette's colours.
  const app = await call("appSettings");
  const palette = app?.palette;
  const dark = app?.values?.mode === "dark" || (app?.values?.mode === "system" && app?.systemDark);
  const vars: Record<string, string> = palette ? (dark ? palette.darkVars : palette.lightVars) : {};
  for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v);
  initZoom();
  await loadZoom();
  on("buildFinished", show);
  on("documentChanged", async () => {
    document.title = (await call("previewWindowTitle")).title;
    await loadZoom();
  });
  show(await call("lastBuild"));
  (window as any).__preview = { ready: true };
}

boot();
