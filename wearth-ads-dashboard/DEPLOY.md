# WEARTH Ads Dashboard — deploy correctly

The live UI at [wearth-ads-dashboard-production](https://wearth-ads-dashboard-production.up.railway.app/) must match `public/prototype.html` (Playfair hero, Drive image, pills, cards, Ad Studio, live grid, FAB).

## Canonical source code

**Repository:** `contactus-ops/wearth-studio`  
**Folder:** `wearth-ads-dashboard/` (this directory)

If you use a **separate GitHub repo** for Railway, mirror or submodule **this folder** and deploy from it. An old Vite scaffold (title “WEARTH ads”, plain centered text) is **not** this app.

## Railway checklist

1. **Service:** `wearth-ads-dashboard` (Node + static `serve`), **not** the Python `web` service.
2. **Monorepo:** set **Root Directory** to `wearth-ads-dashboard` (or connect only the dashboard repo that contains these files).
3. **Build:** uses `railway.toml` + `Dockerfile` here (Node 22, `npm ci`, `npm run build`).
4. **Variable:** `VITE_API_BASE=https://web-production-448c1.up.railway.app` (or your API host).

## Verify after build

`npm run build` runs `scripts/verify-dashboard-ui.mjs` and **fails** if the JS bundle does not include `ad command centre`, `Pending Approval`, and `Ad Studio`. If that fails, you are not building this codebase.

## Static reference

Open `public/prototype.html` locally in a browser for pixel reference without React.
