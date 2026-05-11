/**
 * Post-build guard: fail if the production bundle does not contain the
 * Command Centre shell copy. Catches deploying an old/wrong repo that
 * still builds (e.g. legacy "WEARTH ads" layout).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const assetsDir = path.join(root, "dist", "assets");

const NEEDLES = ["Founder Ad Cockpit", "Live Ad Capsules", "What The Machine Sees"];

function main() {
  if (!fs.existsSync(assetsDir)) {
    console.error("verify-dashboard-ui: missing dist/assets — run vite build first.");
    process.exit(1);
  }
  const jsFiles = fs.readdirSync(assetsDir).filter((f) => f.endsWith(".js"));
  if (!jsFiles.length) {
    console.error("verify-dashboard-ui: no JS chunks in dist/assets.");
    process.exit(1);
  }
  const haystack = jsFiles
    .map((f) => fs.readFileSync(path.join(assetsDir, f), "utf8"))
    .join("\n");
  for (const n of NEEDLES) {
    if (!haystack.includes(n)) {
      console.error(
        `verify-dashboard-ui: bundle missing expected string "${n}". ` +
          `You may be building the wrong source tree (sync from wearth-studio / wearth-ads-dashboard).`,
      );
      process.exit(1);
    }
  }
  console.log("verify-dashboard-ui: OK (founder cockpit strings present in bundle).");
}

main();
