/** The apps in this web project, in the order the hamburger panel lists them. `folder` is the app's
 * folder under webapps/, which is also its page's path. */
export const APPS = [
  { folder: "static_inflater", label: "Static Inflater" },
  { folder: "net_builder", label: "Net Builder" },
  { folder: "interactive_inflater", label: "Interactive Inflater" },
] as const;

export type AppFolder = (typeof APPS)[number]["folder"];

/**
 * Adds the hamburger button (left of the menu bar's first menu) and its left-hand panel of app tabs.
 * `current` is the app this page belongs to; its tab is highlighted.
 */
export function mountAppNav(current: AppFolder) {
  const menubar = document.getElementById("menubar")!;
  const hamburger = document.createElement("button");
  hamburger.id = "hamburger";
  hamburger.type = "button";
  hamburger.textContent = "\u2630";
  hamburger.setAttribute("aria-label", "Apps");
  hamburger.setAttribute("aria-expanded", "false");
  menubar.prepend(hamburger);

  const panel = document.createElement("aside");
  panel.id = "app-panel";
  panel.hidden = true;
  const heading = document.createElement("div");
  heading.className = "app-panel-heading";
  heading.textContent = "Apps";
  panel.append(heading);
  for (const app of APPS) {
    const tab = document.createElement("a");
    tab.className = "app-tab";
    tab.href = `../${app.folder}/index.html`;
    tab.textContent = app.label;
    if (app.folder === current) {
      tab.classList.add("current");
      tab.setAttribute("aria-current", "page");
    }
    panel.append(tab);
  }
  document.body.appendChild(panel);

  const setOpen = (open: boolean) => {
    panel.hidden = !open;
    hamburger.setAttribute("aria-expanded", String(open));
  };
  hamburger.addEventListener("click", () => setOpen(panel.hidden));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setOpen(false);
  });
  document.addEventListener("pointerdown", (e) => {
    if (!panel.hidden && !panel.contains(e.target as Node) && e.target !== hamburger) setOpen(false);
  });
}

/**
 * Shows the page once the app has finished its first layout. Until then `#app` stays hidden
 * (see style.css), so nothing visibly moves into place. Call it after the app's initial work.
 */
export function revealPage() {
  requestAnimationFrame(() => requestAnimationFrame(() => document.documentElement.classList.add("ready")));
}
