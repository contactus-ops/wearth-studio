/* TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — Shai's ad command centre */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  msUntilNextMonday7amIST,
  nextMonday7amIST,
  formatDuration,
} from "./nextMonday";
import "./App.css";

const API =
  import.meta.env.VITE_API_BASE ?? "https://web-production-448c1.up.railway.app";

const HERO_BG =
  "https://drive.google.com/uc?export=view&id=1dpoCxKQ02eK2XmnOZvYaW3EeKmQFz3r2";

const META_ADS_URL =
  "https://adsmanager.facebook.com/adsmanager/manage/ads?act=8979315238856807";

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
  impressions?: number;
  roas?: number | null;
  cpm?: number | null;
  cpc?: number | null;
  error?: string;
  ads_manager_url?: string;
};

type ChartRow = {
  date: string;
  women_spend: number;
  men_spend: number;
  women_clicks: number;
  men_clicks: number;
};

type LivePayload = {
  ok: boolean;
  campaign?: {
    name?: string;
    status?: string;
    effective_status?: string;
    error?: string;
  };
  today_spend?: number | null;
  weekly_roas?: number | null;
  active_ads_count?: number | null;
  adsets: LiveAdset[];
  chart: ChartRow[];
};

type Toast = { id: number; kind: "ok" | "err"; msg: string };

function fmtInr(n: number | null | undefined, fraction = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: fraction,
    minimumFractionDigits: fraction,
  }).format(n);
}

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

function ClockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 7v6l4 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function PendingEmptyState() {
  const [ms, setMs] = useState(() => msUntilNextMonday7amIST());
  useEffect(() => {
    const t = setInterval(
      () => setMs(msUntilNextMonday7amIST()),
      1000
    );
    return () => clearInterval(t);
  }, []);
  const target = useMemo(() => nextMonday7amIST(), []);
  return (
    <div className="empty-pending">
      <p className="empty-title brand-serif">Next ad drops Monday 7am</p>
      <p className="empty-sub">
        Countdown to {target.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", weekday: "long", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}
      </p>
      <div className="countdown mono">{formatDuration(ms)}</div>
    </div>
  );
}

function AdCard({
  ad,
  onRefresh,
  pushToast,
}: {
  ad: PendingAd;
  onRefresh: () => void;
  pushToast: (kind: "ok" | "err", msg: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [headline, setHeadline] = useState(ad.headline ?? "");
  const [body, setBody] = useState(ad.body ?? "");
  const [cta, setCta] = useState(ad.cta ?? "");

  const act = async (kind: "approve" | "reject") => {
    const label = kind === "approve" ? "approve" : "reject";
    setBusy(label);
    try {
      const path =
        kind === "approve"
          ? `/api/ads/approve/${encodeURIComponent(ad.ad_id)}`
          : `/api/ads/reject/${encodeURIComponent(ad.ad_id)}`;
      await jfetch(path, { method: "POST" });
      pushToast("ok", kind === "approve" ? "Approved and live in Meta." : "Ad rejected.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(null);
    }
  };

  const saveEdit = async () => {
    setBusy("save");
    try {
      await jfetch(`/api/ads/edit/${encodeURIComponent(ad.ad_id)}`, {
        method: "PUT",
        body: JSON.stringify({ headline, body, cta }),
      });
      pushToast("ok", "Edits saved.");
      setEditing(false);
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(null);
    }
  };

  const roasNum =
    typeof ad.predicted_roas === "number" ? ad.predicted_roas : null;
  const roasHigh = roasNum != null && roasNum >= 3.5;

  return (
    <article className="pending-card">
      <div className="reasoning-block">
        <p className="reasoning-text">{ad.reasoning || "—"}</p>
      </div>

      <h2 className="card-headline brand-serif">{ad.headline || "Untitled"}</h2>
      <p className="card-body">{ad.body}</p>

      <div className="pill-row">
        <span className="pill cta-pill">{ad.cta || "—"}</span>
        <span className="pill aud-pill">{ad.audience_summary || "—"}</span>
        <span className="pill time-pill">
          <ClockIcon />
          {ad.scheduled_hour != null ? `${ad.scheduled_hour}:00 IST` : "—"}
        </span>
        <span className={`pill roas-pill ${roasHigh ? "roas-high" : "roas-low"}`}>
          Pred. ROAS {roasNum != null ? roasNum.toFixed(1) : "—"}
        </span>
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
            <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          <label>
            CTA
            <input value={cta} onChange={(e) => setCta(e.target.value)} />
          </label>
          <div className="edit-actions">
            <button type="button" className="btn-sage" disabled={!!busy} onClick={saveEdit}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button type="button" className="btn-ghost" disabled={!!busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="btn-stack">
        <button
          type="button"
          className="btn-charcoal"
          disabled={!!busy}
          onClick={() => act("approve")}
        >
          {busy === "approve" ? "Approving…" : "APPROVE"}
        </button>
        <button
          type="button"
          className="btn-sage"
          disabled={!!busy || editing}
          onClick={() => setEditing(true)}
        >
          EDIT
        </button>
        <button
          type="button"
          className="btn-red-muted"
          disabled={!!busy}
          onClick={() => act("reject")}
        >
          {busy === "reject" ? "Rejecting…" : "REJECT"}
        </button>
      </div>

      <a
        className="btn-meta"
        href={META_ADS_URL}
        target="_blank"
        rel="noopener noreferrer"
      >
        VIEW IN META
      </a>
    </article>
  );
}

function SkeletonHero() {
  return (
    <div className="skel-hero">
      <div className="skel skel-line lg" />
      <div className="skel row">
        <div className="skel skel-pill" />
        <div className="skel skel-pill" />
        <div className="skel skel-pill" />
      </div>
    </div>
  );
}

export default function App() {
  const [pending, setPending] = useState<PendingAd[]>([]);
  const [live, setLive] = useState<LivePayload | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activating, setActivating] = useState(false);
  const [injecting, setInjecting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [updatedAt, setUpdatedAt] = useState(() => new Date());

  const pushToast = useCallback((kind: "ok" | "err", text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg: text }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4500);
  }, []);

  const load = useCallback(async () => {
    setRefreshing(true);
    setMsg(null);
    try {
      const [p, l] = await Promise.all([
        jfetch<{ ads: PendingAd[] }>("/api/ads/pending"),
        jfetch<LivePayload>("/api/meta/adsets-live"),
      ]);
      setPending(p.ads ?? []);
      setLive(l);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
      setRefreshing(false);
      setUpdatedAt(new Date());
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [load]);

  const campaignPaused = useMemo(() => {
    const es = (live?.campaign?.effective_status ?? "").toUpperCase();
    return es === "PAUSED" || es.includes("CAMPAIGN_PAUSED");
  }, [live]);

  const activateCampaign = async () => {
    setActivating(true);
    try {
      await jfetch("/api/meta/activate-campaign", {
        method: "POST",
        body: JSON.stringify({}),
      });
      pushToast("ok", "Campaign activation requested.");
      await load();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Activation failed");
    } finally {
      setActivating(false);
    }
  };

  const injectTestAd = async () => {
    setInjecting(true);
    const ad_id = `wearth-inject-${Date.now()}`;
    try {
      await jfetch("/api/ads/pending", {
        method: "POST",
        body: JSON.stringify({
          ad_id,
          headline: "that sticky feeling after a workout.",
          body:
            "It is not just sweat. It is plastic. WEARTH is made from plant-based fabric that breathes the way your body does.",
          cta: "shop now",
          audience_summary: "Women 24-38 Mumbai yoga pilates",
          scheduled_hour: 19,
          reasoning:
            "Sunday evening post-workout golden hour. Mumbai fitness crowd peaks 7-9pm. Pilates and yoga interest stack historically 2.3x higher CTR than gym-only.",
          predicted_roas: 4.1,
        }),
      });
      pushToast("ok", "Test ad added to queue.");
      await load();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Inject failed");
    } finally {
      setInjecting(false);
    }
  };

  const chartData = live?.chart ?? [];

  return (
    <div className="dash">
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.msg}
          </div>
        ))}
      </div>

      <button
        type="button"
        className="fab-inject"
        onClick={injectTestAd}
        disabled={injecting}
        title="Inject test ad"
      >
        {injecting ? "…" : "Inject test ad"}
      </button>

      <header
        className="hero"
        style={{ backgroundImage: `linear-gradient(105deg, rgba(26,26,24,0.72) 0%, rgba(245,240,232,0.45) 45%, rgba(245,240,232,0.85) 100%), url(${HERO_BG})` }}
      >
        <div className="hero-inner">
          <h1 className="wordmark brand-serif">WEARTH</h1>
          <p className="hero-sub">ad command centre</p>
          {loading ? (
            <SkeletonHero />
          ) : (
            <div className="metric-pills">
              <div className="metric-pill">
                <span className="metric-label">Active ads</span>
                <span className="metric-value mono">
                  {live?.active_ads_count ?? "—"}
                </span>
              </div>
              <div className="metric-pill">
                <span className="metric-label">Spend today</span>
                <span className="metric-value mono">
                  {fmtInr(live?.today_spend ?? undefined)}
                </span>
              </div>
              <div className="metric-pill">
                <span className="metric-label">Weekly ROAS</span>
                <span className="metric-value mono">
                  {live?.weekly_roas != null && !Number.isNaN(live.weekly_roas)
                    ? live.weekly_roas.toFixed(2)
                    : "—"}
                </span>
              </div>
            </div>
          )}
        </div>
      </header>

      {campaignPaused && (
        <div className="paused-banner">
          <span>Campaign paused — click to activate</span>
          <button type="button" disabled={activating} onClick={activateCampaign}>
            {activating ? "Activating…" : "Activate campaign"}
          </button>
        </div>
      )}

      <main className="main-content">
        {msg && <div className="banner-err">{msg}</div>}

        <section className="section">
          <h2 className="section-title brand-serif">Pending approvals</h2>
          {!loading && pending.length === 0 && <PendingEmptyState />}
          <div className="pending-grid">
            {pending.map((ad) => (
              <AdCard key={ad.ad_id} ad={ad} onRefresh={load} pushToast={pushToast} />
            ))}
          </div>
        </section>

        <section className="section">
          <h2 className="section-title brand-serif">Live campaigns</h2>
          <p className="section-hint">Last 7 days · Meta insights</p>
          {loading ? (
            <div className="live-two skel-grid">
              <div className="skel skel-card" />
              <div className="skel skel-card" />
            </div>
          ) : (
            <div className="live-two">
              {(live?.adsets ?? []).map((a) => (
                <div key={a.adset_id ?? a.label} className="live-card">
                  <div className="live-card-head">
                    <h3 className="brand-serif">{a.name ?? a.label}</h3>
                    {a.error ? (
                      <span className="badge badge-err">{a.error}</span>
                    ) : (
                      <span
                        className={`badge ${
                          (a.status ?? "").includes("ACTIVE")
                            ? "badge-ok"
                            : "badge-bad"
                        }`}
                      >
                        {a.status ?? "—"}
                      </span>
                    )}
                  </div>
                  {!a.error && (
                    <>
                      <div className="stat-grid">
                        <div>
                          <span className="stat-k">Spend (7d)</span>
                          <span className="stat-v">{fmtInr(a.spend)}</span>
                        </div>
                        <div>
                          <span className="stat-k">Clicks</span>
                          <span className="stat-v">{a.clicks ?? "—"}</span>
                        </div>
                        <div>
                          <span className="stat-k">ROAS</span>
                          <span className="stat-v">
                            {a.roas != null ? a.roas.toFixed(2) : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="stat-k">CPM</span>
                          <span className="stat-v">
                            {a.cpm != null ? fmtInr(a.cpm, 2) : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="stat-k">CPC</span>
                          <span className="stat-v">
                            {a.cpc != null ? fmtInr(a.cpc, 2) : "—"}
                          </span>
                        </div>
                      </div>
                      {a.ads_manager_url && (
                        <a
                          className="btn-meta-outline"
                          href={a.ads_manager_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Open in Ads Manager
                        </a>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="section chart-section">
          <h2 className="section-title brand-serif">Performance · last 7 days</h2>
          {!loading && chartData.length > 0 ? (
            <>
              <h4 className="chart-sub">Spend</h4>
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e8e4dc" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#6b6864" />
                    <YAxis tick={{ fontSize: 11 }} stroke="#6b6864" />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="women_spend" name="Women spend" stroke="#8A9B78" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="men_spend" name="Men spend" stroke="#1A1A18" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <h4 className="chart-sub">Clicks</h4>
              <div className="chart-box">
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e8e4dc" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#6b6864" />
                    <YAxis tick={{ fontSize: 11 }} stroke="#6b6864" />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="women_clicks" name="Women clicks" stroke="#8A9B78" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="men_clicks" name="Men clicks" stroke="#1A1A18" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            !loading && <p className="muted">No chart data yet.</p>
          )}
        </section>
      </main>

      <footer className="dash-footer">
        <span className="mono">
          Last updated{" "}
          {updatedAt.toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata",
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
        <button type="button" className="btn-ghost-footer" disabled={refreshing} onClick={() => load()}>
          {refreshing ? "Refreshing…" : "Refresh data"}
        </button>
        <span className="footer-copy brand-serif">WEARTH © 2026</span>
      </footer>
    </div>
  );
}
