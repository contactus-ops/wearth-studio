/* TARGET ROAS 4:1 AT ₹15K/MONTH SPEND */
import { useCallback, useEffect, useState } from "react";
import "./App.css";

const API =
  import.meta.env.VITE_API_BASE ?? "https://web-production-448c1.up.railway.app";

type PendingAd = {
  ad_id: string;
  adset_id?: string;
  campaign_id?: string;
  video_id?: string;
  headline?: string;
  body?: string;
  cta?: string;
  audience_summary?: string;
  scheduled_hour?: number;
  reasoning?: string;
  predicted_roas?: number;
  creative_url?: string;
  status?: string;
};

type LiveAdset = {
  label?: string;
  adset_id?: string;
  name?: string;
  status?: string;
  spend?: number;
  clicks?: number;
  roas?: number | null;
  error?: string;
};

async function jfetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error((data as { error?: string }).error || r.statusText);
  }
  return data as T;
}

function AdCard({
  ad,
  onRefresh,
}: {
  ad: PendingAd;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [headline, setHeadline] = useState(ad.headline ?? "");
  const [body, setBody] = useState(ad.body ?? "");
  const [cta, setCta] = useState(ad.cta ?? "");

  const act = async (kind: "approve" | "reject") => {
    setBusy(true);
    setErr(null);
    try {
      const path =
        kind === "approve"
          ? `/api/ads/approve/${encodeURIComponent(ad.ad_id)}`
          : `/api/ads/reject/${encodeURIComponent(ad.ad_id)}`;
      await jfetch(path, {
        method: "POST",
      });
      onRefresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await jfetch(`/api/ads/edit/${encodeURIComponent(ad.ad_id)}`, {
        method: "PUT",
        body: JSON.stringify({ headline, body, cta }),
      });
      setEditing(false);
      onRefresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const roas =
    typeof ad.predicted_roas === "number"
      ? ad.predicted_roas.toFixed(2)
      : "—";

  return (
    <article className="card">
      <div className="card-head">
        <div style={{ flex: 1, minWidth: 0 }}>
          {ad.creative_url ? (
            <img
              className="thumb"
              src={ad.creative_url}
              alt=""
              loading="lazy"
            />
          ) : (
            <div
              className="thumb placeholder-thumb"
              style={{ maxWidth: "200px" }}
            >
              Video / creative
            </div>
          )}
        </div>
        <span className="roas-badge">Predicted ROAS {roas}</span>
      </div>
      <div className="copy-block brand-serif">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.35rem" }}>
          {ad.headline || "Untitled"}
        </h2>
      </div>
      <div className="copy-block">
        <p>{ad.body}</p>
      </div>
      <div className="meta-row">
        <strong>CTA:</strong> {ad.cta}
      </div>
      <div className="meta-row">
        <strong>Audience:</strong> {ad.audience_summary}
      </div>
      <div className="meta-row">
        <strong>Scheduled hour:</strong> {ad.scheduled_hour ?? "—"}
      </div>
      <div className="copy-block">
        <h3>Reasoning</h3>
        <p>{ad.reasoning}</p>
      </div>
      <div className="meta-row" style={{ fontSize: "0.8rem" }}>
        ad_id {ad.ad_id}
      </div>

      {editing && (
        <div className="edit-fields">
          <label>
            Headline
            <input
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
            />
          </label>
          <label>
            Body
            <textarea
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </label>
          <label>
            CTA
            <input value={cta} onChange={(e) => setCta(e.target.value)} />
          </label>
        </div>
      )}

      {err && <div className="err">{err}</div>}

      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={busy}
          onClick={() => act("approve")}
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => (editing ? saveEdit() : setEditing(true))}
        >
          {editing ? "Save" : "Edit"}
        </button>
        {editing && (
          <button type="button" disabled={busy} onClick={() => setEditing(false)}>
            Cancel edit
          </button>
        )}
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => act("reject")}
        >
          Reject
        </button>
      </div>
    </article>
  );
}

export default function App() {
  const [pending, setPending] = useState<PendingAd[]>([]);
  const [live, setLive] = useState<LiveAdset[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setMsg(null);
    try {
      const [p, l] = await Promise.all([
        jfetch<{ ads: PendingAd[] }>("/api/ads/pending"),
        jfetch<{ adsets: LiveAdset[] }>("/api/meta/adsets-live"),
      ]);
      setPending(p.ads ?? []);
      setLive(l.adsets ?? []);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="app-wrap">
      <header>
        <h1 className="brand-serif">WEARTH ads</h1>
        <p>Pending approvals and live Meta ad sets — target ROAS 4:1 at ₹15k/month spend.</p>
      </header>

      {loading && <p className="loading">Loading…</p>}
      {msg && <p className="err">{msg}</p>}

      <section>
        <h2 className="brand-serif">Pending</h2>
        {!loading && pending.length === 0 && (
          <p className="loading">No pending ads.</p>
        )}
        <div className="cards">
          {pending.map((ad) => (
            <AdCard key={ad.ad_id} ad={ad} onRefresh={load} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="brand-serif">Live campaigns</h2>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginTop: "-0.5rem" }}>
          Last 7 days · spend and ROAS from Meta insights
        </p>
        <div className="live-grid">
          {live.map((a) => (
            <div key={a.adset_id ?? a.label} className="live-card">
              <h3 className="brand-serif">
                {(a.label ?? "?").toUpperCase()} · {a.name ?? a.adset_id}
              </h3>
              {a.error ? (
                <p className="err">{a.error}</p>
              ) : (
                <>
                  <div className="stat">
                    <span>Status</span>
                    <span>{a.status ?? "—"}</span>
                  </div>
                  <div className="stat">
                    <span>Spend (₹)</span>
                    <span>{a.spend?.toFixed?.(2) ?? "—"}</span>
                  </div>
                  <div className="stat">
                    <span>Clicks</span>
                    <span>{a.clicks ?? "—"}</span>
                  </div>
                  <div className="stat">
                    <span>ROAS</span>
                    <span>
                      {a.roas != null ? a.roas.toFixed(2) : "—"}
                    </span>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
