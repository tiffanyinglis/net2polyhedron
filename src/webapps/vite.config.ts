import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

const INPUTS_DIR = fileURLToPath(new URL("./data/inputs", import.meta.url));
const OUTPUTS_DIR = fileURLToPath(new URL("./data/outputs", import.meta.url));
const OUTPUT_NAME = /^[A-Za-z0-9_.-]+\.hippo$/;
/** Dev-only endpoints for Run All and the Viewer: list the .poly nets in data/inputs/, list the
 * saved sessions in data/outputs/, and write sessions there. A browser can't touch the project
 * folder itself, so the dev server does it. */
function batchRunEndpoints(): Plugin {
  return {
    name: "batch-run-endpoints",
    configureServer(server) {
      server.middlewares.use("/api/inputs", (_req, res) => {
        const names = fs.readdirSync(INPUTS_DIR).filter((f) => f.endsWith(".poly")).sort();
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(names));
      });
      server.middlewares.use("/api/output-names", (_req, res) => {
        const names = fs.existsSync(OUTPUTS_DIR)
          ? fs.readdirSync(OUTPUTS_DIR).filter((f) => OUTPUT_NAME.test(f)).sort()
          : [];
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(names));
      });
      server.middlewares.use("/api/outputs", (req, res) => {
        const name = decodeURIComponent((req.url ?? "").replace(/^\//, ""));
        if (req.method !== "POST" || !OUTPUT_NAME.test(name)) {
          res.statusCode = 400;
          res.end("expected POST /api/outputs/<name>.hippo");
          return;
        }
        const chunks: Buffer[] = [];
        req.on("data", (chunk: Buffer) => chunks.push(chunk));
        req.on("end", () => {
          fs.mkdirSync(OUTPUTS_DIR, { recursive: true });
          fs.writeFileSync(`${OUTPUTS_DIR}/${name}`, Buffer.concat(chunks));
          res.end("ok");
        });
      });
    },
  };
}

export default defineConfig({
  root: ".",
  base: "./",
  // Static net files live in data/ (served at the site root: data/inputs/x.poly -> /inputs/x.poly).
  publicDir: "data",
  build: {
    outDir: "dist",
    // One page per app (plus the root redirect), so each app can be built and opened on its own.
    rollupOptions: {
      input: Object.fromEntries(
        ["index.html", "static_inflater/index.html", "net_builder/index.html", "interactive_inflater/index.html"].map(
          (page) => [page.replace(/(\/index)?\.html$/, "") || "index", fileURLToPath(new URL(`./${page}`, import.meta.url))],
        ),
      ),
    },
  },
  plugins: [batchRunEndpoints()],
});
