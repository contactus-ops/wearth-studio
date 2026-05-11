/* TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — layout matches public/prototype.html */
import { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";

const API =
  import.meta.env.VITE_API_BASE ?? "https://web-production-448c1.up.railway.app";

const META_ADS_URL =
  "https://adsmanager.facebook.com/adsmanager/manage/ads?act=8979315238856807";

type PendingAd = {
  ad_id: string;
  headline?: string;
  body?: string;
  cta?: string;
  audience_summary?: string;
  scheduled_hour?: number;
  reasoning?: string;
  predicted_roas?: number;
  creative_url?: string;
  /** Meta CDN URL from GET /api/ads/pending when video_id is set (server-resolved). */
  thumbnail_url?: string;
  video_id?: string;
  feedback_worked?: string;
  feedback_didnt?: string;
  status?: string;
};

type LiveAdset = {
  label?: string;
  adset_id?: string;
  name?: string;
  status?: string;
  spend?: number;
  spend_alltime?: number;
  spend_today?: number;
  impressions_today?: number;
  clicks_today?: number;
  impressions_alltime?: number;
  clicks_alltime?: number;
  clicks?: number;
  impressions?: number;
  roas?: number | null;
  cpm?: number | null;
  cpc?: number | null;
  error?: string;
  ads_manager_url?: string;
};

type LivePayload = {
  ok: boolean;
  insights_adset_alltime_preset?: string;
  insights_adset_today_preset?: string;
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
};

type AutomationPayload = {
  ok?: boolean;
  generated_at?: string;
  eligible_to_act?: boolean;
  route?: { route?: string; action?: string; reason?: string };
  sleep_window?: { not_before_utc?: string | null; remaining_seconds?: number };
  budget_guardrails?: {
    planned_total_daily_budget_inr?: number;
    max_new_ads_per_cycle?: number;
  };
  safe_plan_summary?: {
    execution_kinds?: Record<string, number>;
    action_types?: Record<string, number>;
  };
  guardrails?: Record<string, boolean>;
};

type DashboardTab = "command" | "video" | "image";

type DriveVideo = {
  id: string;
  name?: string;
  thumbnail?: string;
  url?: string;
};

type DriveImage = { id: string; name?: string; url?: string };

type Toast = { id: number; kind: "ok" | "err"; msg: string };

function fmtInr(n: number | null | undefined, frac = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: frac,
    minimumFractionDigits: frac,
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

function isMetaNumericId(s: string | undefined): boolean {
  const t = (s || "").trim();
  return t.length > 0 && /^\d+$/.test(t);
}

function PendingCard({
  ad,
  onRefresh,
  pushToast,
}: {
  ad: PendingAd;
  onRefresh: () => void;
  pushToast: (k: "ok" | "err", m: string) => void;
}) {
  const [studioOpen, setStudioOpen] = useState(false);
  const [headline, setHeadline] = useState(ad.headline ?? "");
  const [body, setBody] = useState(ad.body ?? "");
  const [cta, setCta] = useState(ad.cta ?? "");
  const [draftVideoId, setDraftVideoId] = useState(ad.video_id ?? "");
  const [draftImageUrl, setDraftImageUrl] = useState(ad.creative_url ?? "");
  const [fbOk, setFbOk] = useState(ad.feedback_worked ?? "");
  const [fbBad, setFbBad] = useState(ad.feedback_didnt ?? "");
  const [aiHead, setAiHead] = useState<string[] | null>(null);
  const [aiBody, setAiBody] = useState<string[] | null>(null);
  const [aiCta, setAiCta] = useState<string[] | null>(null);
  const [showAiHead, setShowAiHead] = useState(false);
  const [showAiBody, setShowAiBody] = useState(false);
  const [showAiCta, setShowAiCta] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [videoModal, setVideoModal] = useState(false);
  const [imageModal, setImageModal] = useState(false);
  const [videos, setVideos] = useState<DriveVideo[]>([]);
  const [images, setImages] = useState<DriveImage[]>([]);
  const [metaLive, setMetaLive] = useState<{
    headline: string;
    body: string;
    thumbnail_url?: string;
    video_id?: string;
  } | null>(null);
  const [metaVideoThumb, setMetaVideoThumb] = useState<string | null>(null);

  useEffect(() => {
    setMetaLive(null);
    setMetaVideoThumb(null);
  }, [ad.ad_id]);

  useEffect(() => {
    if (
      isMetaNumericId(ad.ad_id) &&
      metaLive &&
      (metaLive.headline.length > 0 || metaLive.body.length > 0)
    ) {
      setHeadline(metaLive.headline || ad.headline || "");
      setBody(metaLive.body || ad.body || "");
    } else {
      setHeadline(ad.headline ?? "");
      setBody(ad.body ?? "");
    }
    setCta(ad.cta ?? "");
    setDraftVideoId(ad.video_id ?? "");
    setDraftImageUrl(ad.creative_url ?? "");
    setFbOk(ad.feedback_worked ?? "");
    setFbBad(ad.feedback_didnt ?? "");
  }, [
    ad.ad_id,
    ad.headline,
    ad.body,
    ad.cta,
    ad.video_id,
    ad.creative_url,
    ad.feedback_worked,
    ad.feedback_didnt,
    metaLive,
  ]);

  useEffect(() => {
    let cancelled = false;
    async function loadMeta() {
      if (!isMetaNumericId(ad.ad_id)) {
        if (!cancelled) setMetaLive(null);
        return;
      }
      try {
        const r = await jfetch<{
          ok?: boolean;
          headline?: string;
          body?: string;
          thumbnail_url?: string;
          video_id?: string;
        }>(`/api/meta/ad-live-creative?ad_id=${encodeURIComponent(ad.ad_id.trim())}`);
        if (cancelled || !r.ok) return;
        setMetaLive({
          headline: (r.headline || "").trim(),
          body: (r.body || "").trim(),
          thumbnail_url: (r.thumbnail_url || "").trim() || undefined,
          video_id: (r.video_id || "").trim() || undefined,
        });
      } catch {
        if (!cancelled) setMetaLive(null);
      }
    }
    loadMeta();
    return () => {
      cancelled = true;
    };
  }, [ad.ad_id]);

  useEffect(() => {
    let cancelled = false;
    const vid = (metaLive?.video_id || draftVideoId || ad.video_id || "").trim();
    async function loadThumb() {
      if (!isMetaNumericId(vid)) {
        if (!cancelled) setMetaVideoThumb(null);
        return;
      }
      try {
        const r = await jfetch<{ ok?: boolean; thumbnail_url?: string | null }>(
          `/api/meta/video-thumbnail?video_id=${encodeURIComponent(vid)}`
        );
        if (cancelled || !r.ok) return;
        setMetaVideoThumb(r.thumbnail_url || null);
      } catch {
        if (!cancelled) setMetaVideoThumb(null);
      }
    }
    loadThumb();
    return () => {
      cancelled = true;
    };
  }, [ad.video_id, draftVideoId, metaLive?.video_id]);

  const roasLabel =
    typeof ad.predicted_roas === "number"
      ? `ROAS ${ad.predicted_roas.toFixed(1)}x`
      : "ROAS —";

  const hourTag =
    ad.scheduled_hour != null ? `${ad.scheduled_hour}:00` : "—";

  const improve = async (field: "headline" | "body" | "cta") => {
    const cur =
      field === "headline" ? headline : field === "body" ? body : cta;
    const setAi =
      field === "headline" ? setAiHead : field === "body" ? setAiBody : setAiCta;
    const setShow =
      field === "headline"
        ? setShowAiHead
        : field === "body"
          ? setShowAiBody
          : setShowAiCta;
    setBusy(`ai-${field}`);
    try {
      const res = await jfetch<{ ok?: boolean; variants?: string[] }>(
        "/api/ads/improve-copy",
        {
          method: "POST",
          body: JSON.stringify({
            field,
            current_text: cur,
            instruction: "",
          }),
        }
      );
      if (!res.variants?.length) throw new Error("No variants returned");
      setAi(res.variants.slice(0, 3));
      setShow(true);
      pushToast("ok", "AI variants ready.");
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "AI failed");
    } finally {
      setBusy(null);
    }
  };

  const openVideos = async () => {
    setVideoModal(true);
    setBusy("list-videos");
    try {
      const r = await jfetch<{ videos?: DriveVideo[] }>("/api/drive/videos");
      setVideos(r.videos ?? []);
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Drive list failed");
      setVideos([]);
    } finally {
      setBusy(null);
    }
  };

  const openImages = async () => {
    setImageModal(true);
    setBusy("list-images");
    try {
      const r = await jfetch<{ images?: DriveImage[] }>("/api/drive/images");
      setImages(r.images ?? []);
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Drive list failed");
      setImages([]);
    } finally {
      setBusy(null);
    }
  };

  const saveCopy = async () => {
    setBusy("save-copy");
    try {
      await jfetch(`/api/ads/edit/${encodeURIComponent(ad.ad_id)}`, {
        method: "PUT",
        body: JSON.stringify({
          headline,
          body,
          cta,
          video_id: draftVideoId,
          creative_url: draftImageUrl,
        }),
      });
      pushToast("ok", "Copy saved.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(null);
    }
  };

  const publish = async () => {
    setBusy("publish");
    try {
      await jfetch(`/api/ads/edit/${encodeURIComponent(ad.ad_id)}`, {
        method: "PUT",
        body: JSON.stringify({
          headline,
          body,
          cta,
          video_id: draftVideoId,
          creative_url: draftImageUrl,
        }),
      });
      await jfetch(`/api/ads/publish/${encodeURIComponent(ad.ad_id)}`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      pushToast("ok", "Published to Meta.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Publish failed");
    } finally {
      setBusy(null);
    }
  };

  const saveFeedback = async () => {
    setBusy("feedback");
    try {
      await jfetch("/api/ads/feedback", {
        method: "POST",
        body: JSON.stringify({
          ad_id: ad.ad_id,
          what_worked: fbOk,
          what_didnt_work: fbBad,
        }),
      });
      pushToast("ok", "Feedback saved.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Feedback failed");
    } finally {
      setBusy(null);
    }
  };

  const approve = async () => {
    setBusy("approve");
    try {
      await jfetch(`/api/ads/approve/${encodeURIComponent(ad.ad_id)}`, {
        method: "POST",
      });
      pushToast("ok", "Approved.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Approve failed");
    } finally {
      setBusy(null);
    }
  };

  const reject = async () => {
    setBusy("reject");
    try {
      await jfetch(`/api/ads/reject/${encodeURIComponent(ad.ad_id)}`, {
        method: "POST",
      });
      pushToast("ok", "Rejected.");
      onRefresh();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Reject failed");
    } finally {
      setBusy(null);
    }
  };

  const driveThumb =
    draftImageUrl ||
    (draftVideoId && !isMetaNumericId(draftVideoId)
      ? `https://drive.google.com/thumbnail?id=${draftVideoId}&sz=w800`
      : "");
  const previewUrl =
    (ad.thumbnail_url && ad.thumbnail_url.trim()) ||
    metaVideoThumb ||
    metaLive?.thumbnail_url ||
    driveThumb ||
    "";

  const cardHeadline =
    (metaLive?.headline && metaLive.headline.length > 0
      ? metaLive.headline
      : ad.headline) || "Untitled";
  const cardBody =
    metaLive?.body && metaLive.body.length > 0 ? metaLive.body : ad.body;

  return (
    <div className="ad-card">
      <div className="reasoning">&ldquo;{ad.reasoning || "—"}&rdquo;</div>
      {metaLive && (metaLive.headline || metaLive.body) ? (
        <div className="meta-live-badge">Live on Meta</div>
      ) : null}
      <div className="ad-headline">{cardHeadline}</div>
      <div className="ad-body">{cardBody}</div>
      {previewUrl ? (
        <div className="pending-creative-hero">
          <img src={previewUrl} alt="" className="pending-creative-hero-img" />
        </div>
      ) : null}
      <div className="pills-row">
        {ad.audience_summary && (
          <span className="tag">{ad.audience_summary}</span>
        )}
        <span className="tag">{hourTag}</span>
        {ad.cta && <span className="tag">{ad.cta}</span>}
        <span className="roas-badge">{roasLabel}</span>
      </div>
      <div className="btn-row">
        <button
          type="button"
          className="btn btn-approve"
          disabled={!!busy}
          onClick={approve}
        >
          {busy === "approve" ? "…" : "APPROVE"}
        </button>
        <button
          type="button"
          className="btn btn-edit"
          disabled={!!busy}
          onClick={() => setStudioOpen((o) => !o)}
        >
          EDIT
        </button>
        <button
          type="button"
          className="btn btn-reject"
          disabled={!!busy}
          onClick={reject}
        >
          {busy === "reject" ? "…" : "REJECT"}
        </button>
      </div>
      <a
        href={META_ADS_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="view-meta"
      >
        View in Meta Ads Manager →
      </a>

      <div className="studio-panel">
        <button
          type="button"
          className="studio-header"
          onClick={() => setStudioOpen((o) => !o)}
        >
          <span>Ad Studio — Review &amp; Edit Creative</span>
          <span>{studioOpen ? "▲" : "▼"}</span>
        </button>
        {studioOpen && (
          <div className="studio-body">
            <div>
              <div className="studio-col-label">Creative</div>
              <div className="creative-preview">
                {previewUrl ? (
                  <img src={previewUrl} alt="" className="creative-preview-img" />
                ) : (
                  "video preview"
                )}
              </div>
              <button
                type="button"
                className="change-btn"
                disabled={!!busy}
                onClick={openVideos}
              >
                Change Video
              </button>
              <button
                type="button"
                className="change-btn"
                disabled={!!busy}
                onClick={openImages}
              >
                Change Image
              </button>
              <div style={{ marginTop: 24 }}>
                <div className="studio-col-label">Audience</div>
                <p className="audience-copy">
                  {ad.audience_summary ||
                    "Targeting details from your ad plan will appear here."}
                </p>
              </div>
              <div className="feedback-section">
                <div className="feedback-label">What worked</div>
                <textarea
                  className="fb-textarea"
                  rows={2}
                  placeholder="e.g. The hook landed well, high CTR on Sunday evening..."
                  value={fbOk}
                  onChange={(e) => setFbOk(e.target.value)}
                />
                <div className="feedback-label" style={{ marginTop: 12 }}>
                  What didn&apos;t work
                </div>
                <textarea
                  className="fb-textarea"
                  rows={2}
                  placeholder="e.g. Too much text in body, lost them at line 3..."
                  value={fbBad}
                  onChange={(e) => setFbBad(e.target.value)}
                />
                <button
                  type="button"
                  className="save-btn"
                  disabled={!!busy}
                  onClick={saveFeedback}
                >
                  {busy === "feedback" ? "Saving…" : "Save feedback"}
                </button>
              </div>
            </div>
            <div>
              <div className="studio-col-label">Copy Editor</div>
              <div className="copy-field">
                <div className="copy-label">Headline</div>
                <textarea
                  className="copy-text"
                  rows={2}
                  value={headline}
                  onChange={(e) => setHeadline(e.target.value)}
                />
                <button
                  type="button"
                  className="ai-btn"
                  disabled={!!busy}
                  onClick={() => improve("headline")}
                >
                  {busy === "ai-headline" ? "…" : "Improve with AI"}
                </button>
                {showAiHead && aiHead && (
                  <div className="ai-suggestions">
                    <div className="ai-suggestion-label">
                      3 variants — click to use
                    </div>
                    {aiHead.map((t, i) => (
                      <button
                        type="button"
                        key={i}
                        className="ai-suggestion"
                        onClick={() => {
                          setHeadline(t);
                          setShowAiHead(false);
                        }}
                      >
                        <span>{t}</span>
                        <span className="use-btn">Use this</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="copy-field">
                <div className="copy-label">Body</div>
                <textarea
                  className="copy-text body-text"
                  rows={4}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                />
                <button
                  type="button"
                  className="ai-btn"
                  disabled={!!busy}
                  onClick={() => improve("body")}
                >
                  {busy === "ai-body" ? "…" : "Improve with AI"}
                </button>
                {showAiBody && aiBody && (
                  <div className="ai-suggestions">
                    <div className="ai-suggestion-label">
                      3 variants — click to use
                    </div>
                    {aiBody.map((t, i) => (
                      <button
                        type="button"
                        key={i}
                        className="ai-suggestion"
                        onClick={() => {
                          setBody(t);
                          setShowAiBody(false);
                        }}
                      >
                        <span>{t}</span>
                        <span className="use-btn">Use this</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="copy-field">
                <div className="copy-label">CTA</div>
                <textarea
                  className="copy-text"
                  rows={1}
                  value={cta}
                  onChange={(e) => setCta(e.target.value)}
                />
                <button
                  type="button"
                  className="ai-btn"
                  disabled={!!busy}
                  onClick={() => improve("cta")}
                >
                  {busy === "ai-cta" ? "…" : "Improve with AI"}
                </button>
                {showAiCta && aiCta && (
                  <div className="ai-suggestions">
                    <div className="ai-suggestion-label">
                      3 variants — click to use
                    </div>
                    {aiCta.map((t, i) => (
                      <button
                        type="button"
                        key={i}
                        className="ai-suggestion"
                        onClick={() => {
                          setCta(t);
                          setShowAiCta(false);
                        }}
                      >
                        <span>{t}</span>
                        <span className="use-btn">Use</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="save-btn"
                style={{ marginBottom: 8 }}
                disabled={!!busy}
                onClick={saveCopy}
              >
                {busy === "save-copy" ? "Saving…" : "Save copy changes"}
              </button>
              <button
                type="button"
                className="publish-btn"
                disabled={!!busy}
                onClick={publish}
              >
                {busy === "publish" ? "Publishing…" : "Publish to Meta"}
              </button>
            </div>
          </div>
        )}
      </div>

      {videoModal && (
        <div
          className="modal-back"
          role="presentation"
          onClick={() => setVideoModal(false)}
        >
          <div
            className="modal-panel"
            role="dialog"
            aria-modal
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3>Pick video</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setVideoModal(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-list">
              {videos.map((v) => (
                <button
                  type="button"
                  key={v.id}
                  className="pick-item"
                  onClick={() => {
                    setDraftVideoId(v.id);
                    setDraftImageUrl("");
                    setVideoModal(false);
                    pushToast("ok", "Video selected (save copy or publish).");
                  }}
                >
                  {v.thumbnail && (
                    <img src={v.thumbnail} alt="" className="pick-thumb" />
                  )}
                  <span>{v.name || v.id}</span>
                </button>
              ))}
              {videos.length === 0 && (
                <p className="empty-note">No videos found.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {imageModal && (
        <div
          className="modal-back"
          role="presentation"
          onClick={() => setImageModal(false)}
        >
          <div
            className="modal-panel"
            role="dialog"
            aria-modal
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3>Pick image</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setImageModal(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-list">
              {images.map((im) => (
                <button
                  type="button"
                  key={im.id}
                  className="pick-item"
                  onClick={() => {
                    setDraftImageUrl(im.url || "");
                    setImageModal(false);
                    pushToast("ok", "Image selected.");
                  }}
                >
                  <img
                    src={im.url}
                    alt=""
                    className="pick-thumb"
                  />
                  <span>{im.name || im.id}</span>
                </button>
              ))}
              {images.length === 0 && (
                <p className="empty-note">No images found.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function LegacyApp() {
  const [pending, setPending] = useState<PendingAd[]>([]);
  const [live, setLive] = useState<LivePayload | null>(null);
  const [automation, setAutomation] = useState<AutomationPayload | null>(null);
  const [activeTab, setActiveTab] = useState<DashboardTab>("command");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activating, setActivating] = useState(false);
  const [injecting, setInjecting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [updatedAt, setUpdatedAt] = useState(() => new Date());

  const pushToast = useCallback((kind: "ok" | "err", msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const automationBody = {
        started_at_utc: "2026-05-11T15:29:23+00:00",
        not_before_utc: "2026-05-17T15:29:23+00:00",
        interval_days: 6,
        target_roas: 4,
        date_preset: "last_7d",
        min_spend_inr: 500,
        total_daily_budget_inr: 2500,
        max_new_ads_per_cycle: 3,
      };
      const [p, l, a] = await Promise.all([
        jfetch<{ ads: PendingAd[] }>("/api/ads/pending"),
        jfetch<LivePayload>("/api/meta/adsets-live"),
        jfetch<AutomationPayload>("/api/automation/ad-machine-tick", {
          method: "POST",
          body: JSON.stringify(automationBody),
        }).catch(() => null),
      ]);
      setPending(p.ads ?? []);
      setLive(l);
      setAutomation(a);
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
      setRefreshing(false);
      setUpdatedAt(new Date());
    }
  }, [pushToast]);

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
      pushToast("ok", "Campaign activated.");
      await load();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Activate failed");
    } finally {
      setActivating(false);
    }
  };

  const injectTest = async () => {
    setInjecting(true);
    const ad_id = `wearth-inject-${Date.now()}`;
    try {
      await jfetch("/api/ads/pending", {
        method: "POST",
        body: JSON.stringify({
          ad_id,
          headline: "that sticky feeling after a workout.",
          body: "It's not just sweat. It's plastic. WEARTH is made from plant-based fabric that breathes the way your body does.",
          cta: "shop now",
          audience_summary: "Women 24-38 Mumbai yoga pilates",
          scheduled_hour: 19,
          reasoning:
            "Sunday evening post-workout golden hour. Mumbai fitness crowd peaks 7-9pm.",
          predicted_roas: 4.1,
        }),
      });
      pushToast("ok", "Test ad injected.");
      await load();
    } catch (e) {
      pushToast("err", e instanceof Error ? e.message : "Inject failed");
    } finally {
      setInjecting(false);
    }
  };

  const heroPills = loading ? (
    <div className="pills skel-hero">
      <div className="pill" />
      <div className="pill" />
      <div className="pill" />
    </div>
  ) : (
    <div className="pills">
      <div className="pill">
        {live?.active_ads_count ?? "—"} active ads
      </div>
      <div className="pill">Today {fmtInr(live?.today_spend ?? 0)}</div>
      <div className="pill">
        Weekly ROAS{" "}
        {live?.weekly_roas != null && !Number.isNaN(live.weekly_roas)
          ? live.weekly_roas.toFixed(2)
          : "—"}
      </div>
    </div>
  );

  return (
    <div className="app-root">
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            {t.msg}
          </div>
        ))}
      </div>

      <button
        type="button"
        className="fab"
        title="Inject test ad"
        disabled={injecting}
        onClick={injectTest}
      >
        +
      </button>

      <div className="hero">
        <h1>WEARTH</h1>
        <p>ad command centre</p>
        {heroPills}
      </div>

      <div className="wrap">
        <div className="brain-tabs" role="tablist" aria-label="WEARTH ad machine tabs">
          <button
            type="button"
            className={`brain-tab ${activeTab === "command" ? "brain-tab-active" : ""}`}
            onClick={() => setActiveTab("command")}
          >
            Ad Dashboard
          </button>
          <button
            type="button"
            className={`brain-tab ${activeTab === "video" ? "brain-tab-active" : ""}`}
            onClick={() => setActiveTab("video")}
          >
            Video Creative Brain
          </button>
          <button
            type="button"
            className={`brain-tab ${activeTab === "image" ? "brain-tab-active" : ""}`}
            onClick={() => setActiveTab("image")}
          >
            Image Creative Brain
          </button>
        </div>

        {activeTab === "command" ? (
          <>
            <div className="automation-card">
              <div>
                <div className="section-label automation-label">Automation Loop</div>
                <h2>{automation?.route?.action ?? "Safe ad machine router"}</h2>
                <p>{automation?.route?.reason ?? "Loading Meta brain status..."}</p>
              </div>
              <div className="automation-grid">
                <div>
                  <span>State</span>
                  <strong>{automation?.eligible_to_act ? "Ready" : "Observing"}</strong>
                </div>
                <div>
                  <span>Next Fire</span>
                  <strong>
                    {automation?.sleep_window?.not_before_utc
                      ? new Date(automation.sleep_window.not_before_utc).toLocaleDateString("en-IN", {
                          timeZone: "Asia/Kolkata",
                          day: "2-digit",
                          month: "short",
                        })
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Budget Guard</span>
                  <strong>{fmtInr(automation?.budget_guardrails?.planned_total_daily_budget_inr)}</strong>
                </div>
                <div>
                  <span>New Ads</span>
                  <strong>{automation?.budget_guardrails?.max_new_ads_per_cycle ?? 3}</strong>
                </div>
              </div>
            </div>

        <div className="section-label">Pending Approval</div>
        {loading ? (
          <div className="skel-card" />
        ) : pending.length === 0 ? (
          <div className="ad-card empty-pending-card">
            <div className="empty-pending-title">Nothing in the queue</div>
            <p className="ad-body" style={{ marginBottom: 12 }}>
              When a creative is pending approval it appears here with the full
              Ad Studio (copy, Drive video/image, AI variants, publish).
            </p>
            <p className="audience-copy">
              Use the <strong>+</strong> button (bottom right) to inject a test ad
              and walk through the flow. Target ROAS 4:1 at ₹15k/month spend.
            </p>
          </div>
        ) : (
          pending.map((ad) => (
            <PendingCard key={ad.ad_id} ad={ad} onRefresh={load} pushToast={pushToast} />
          ))
        )}

        <div className="section-label">Live Campaigns</div>
        {loading ? (
          <div className="live-grid">
            <div className="skel-card" />
            <div className="skel-card" />
          </div>
        ) : (
          <div className="live-grid">
            {(live?.adsets ?? []).map((a) => (
              <div key={a.adset_id ?? a.label} className="live-card">
                <div className="live-label">{(a.label ?? "?").toUpperCase()}</div>
                <div className="live-name">{a.name ?? a.adset_id}</div>
                {a.error ? (
                  <span className="status-badge status-paused">
                    <span className="dot dot-paused" />
                    {a.error}
                  </span>
                ) : (
                  <span
                    className={`status-badge ${
                      (a.status ?? "").includes("ACTIVE")
                        ? "status-active"
                        : "status-paused"
                    }`}
                  >
                    <span
                      className={`dot ${
                        (a.status ?? "").includes("ACTIVE")
                          ? "dot-active"
                          : "dot-paused"
                      }`}
                    />
                    {campaignPaused ? "Campaign paused" : a.status ?? "—"}
                  </span>
                )}
                {campaignPaused && (
                  <div className="paused-banner">
                    <p>Campaign paused — activate to start spending</p>
                    <button
                      type="button"
                      className="activate-btn"
                      disabled={activating}
                      onClick={activateCampaign}
                    >
                      {activating ? "…" : "Activate"}
                    </button>
                  </div>
                )}
                {!a.error && (
                  <>
                    <div className="live-spend-hero">
                      <div className="live-spend-today">
                        {fmtInr(a.spend_today ?? 0)}
                      </div>
                      <div className="live-spend-today-cap">Today</div>
                      <div className="live-spend-alltime">
                        {fmtInr(
                          a.spend_alltime ??
                            a.spend ??
                            0,
                        )}{" "}
                        <span className="live-spend-alltime-tag">all-time</span>
                      </div>
                      <div className="live-intraday">
                        {(a.impressions_today ?? 0).toLocaleString("en-IN")} imps
                        today · {(a.clicks_today ?? 0).toLocaleString("en-IN")}{" "}
                        clicks today
                      </div>
                    </div>
                    <div className="metrics-grid">
                      <div className="metric">
                        <div className="metric-val">
                          {(a.impressions_alltime ?? a.impressions ?? 0).toLocaleString(
                            "en-IN",
                          )}
                        </div>
                        <div className="metric-label">Impressions (all-time)</div>
                      </div>
                      <div className="metric">
                        <div className="metric-val">
                          {(a.clicks_alltime ?? a.clicks ?? 0).toLocaleString("en-IN")}
                        </div>
                        <div className="metric-label">Clicks (all-time)</div>
                      </div>
                      <div className="metric">
                        <div className="metric-val">
                          {a.roas != null ? a.roas.toFixed(2) : "—"}
                        </div>
                        <div className="metric-label">ROAS</div>
                      </div>
                      <div className="metric">
                        <div className="metric-val">
                          {a.cpm != null ? fmtInr(a.cpm, 2) : "—"}
                        </div>
                        <div className="metric-label">CPM</div>
                      </div>
                      <div className="metric">
                        <div className="metric-val">
                          {a.cpc != null ? fmtInr(a.cpc, 2) : "—"}
                        </div>
                        <div className="metric-label">CPC</div>
                      </div>
                    </div>
                  </>
                )}
                {a.ads_manager_url && (
                  <a
                    href={a.ads_manager_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="meta-link"
                  >
                    Open in Meta Ads Manager →
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
          </>
        ) : (
          <div className="brain-panel">
            <div className="section-label">
              {activeTab === "video" ? "Video Creative Brain" : "Image Creative Brain"}
            </div>
            <h2>
              {activeTab === "video"
                ? "Raw video to judged Meta-ready output"
                : "Raw image to judged Meta-ready output"}
            </h2>
            <p>
              This tab is reserved for founder uploads, iteration history, parent judge scores,
              and final approved outputs. The backend brains are live; the next UI slice will add
              upload controls and one-click processing for Shai.
            </p>
            <div className="brain-steps">
              <span>Upload raw asset</span>
              <span>Brain diagnosis</span>
              <span>Repair / production</span>
              <span>Parent judge</span>
              <span>Approved output</span>
            </div>
          </div>
        )}
      </div>

      <div className="footer">
        <div className="footer-meta">
          Last updated{" "}
          {updatedAt.toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata",
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </div>
        <div className="footer-brand">WEARTH</div>
        <button
          type="button"
          className="refresh-btn"
          disabled={refreshing}
          onClick={() => load()}
        >
          {refreshing ? "…" : "Refresh data"}
        </button>
      </div>
    </div>
  );
}

type CampaignMetric = {
  spend_inr?: number;
  impressions?: number;
  clicks?: number;
  ctr?: number | null;
  cpc_inr?: number | null;
  cpm_inr?: number | null;
  purchases?: number;
  purchase_value_inr?: number | null;
  roas?: number | null;
};

type CampaignAd = {
  id: string;
  name?: string;
  status?: string;
  effective_status?: string;
  created_time?: string;
  updated_time?: string;
  ads_manager_url?: string;
  adset_id?: string;
  adset_name?: string;
  adset_status?: string;
  adset_stage?: string;
  adset_daily_budget_inr?: number | null;
  metrics?: CampaignMetric;
  creative?: {
    id?: string;
    name?: string;
    title?: string;
    body?: string;
    thumbnail_url?: string;
    image_url?: string;
    video_id?: string;
  };
};

type CampaignAdset = CampaignMetric & {
  adset_id?: string;
  name?: string;
  status?: string;
  effective_status?: string;
  daily_budget_inr?: number | null;
  daily_budget_paise?: number;
  stage?: string;
  ad_count?: number;
  active_ad_count?: number;
  ads_manager_url?: string;
  ads?: CampaignAd[];
};

type CampaignDashboard = {
  ok?: boolean;
  date_preset?: string;
  campaign?: {
    id?: string;
    name?: string;
    status?: string;
    effective_status?: string;
    objective?: string;
    buying_type?: string;
  };
  totals?: CampaignMetric & {
    active_ads?: number;
    active_adsets?: number;
  };
  adsets?: CampaignAdset[];
  ads?: CampaignAd[];
  brain?: {
    summary?: string;
    urgency?: string;
    recommended_actions?: Array<{
      action_type?: string;
      adset_id?: string;
      priority?: string;
      reason?: string;
      proposed_daily_budget_paise?: number | null;
    }>;
  };
  guardrails?: Record<string, boolean | string>;
  errors?: Array<Record<string, unknown>>;
};

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}%`;
}

function compact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-IN", { notation: "compact" }).format(n);
}

function statusClass(status?: string): string {
  const s = (status || "").toUpperCase();
  if (s.includes("ACTIVE")) return "cockpit-status-active";
  if (s.includes("REVIEW") || s.includes("PROCESS")) return "cockpit-status-review";
  return "cockpit-status-paused";
}

function MetricTile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`cockpit-metric ${tone ? `cockpit-metric-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AdRow({ ad }: { ad: CampaignAd }) {
  const [open, setOpen] = useState(false);
  const m = ad.metrics || {};
  const creative = ad.creative || {};
  return (
    <div className="cockpit-ad">
      <button type="button" className="cockpit-ad-main" onClick={() => setOpen((v) => !v)}>
        <div className="cockpit-thumb">
          {creative.thumbnail_url || creative.image_url ? (
            <img src={creative.thumbnail_url || creative.image_url} alt="" />
          ) : (
            <span>No preview</span>
          )}
        </div>
        <div className="cockpit-ad-copy">
          <div className="cockpit-row-top">
            <span className={`cockpit-status ${statusClass(ad.effective_status || ad.status)}`}>
              {ad.effective_status || ad.status || "UNKNOWN"}
            </span>
            <span>{ad.id}</span>
            {ad.adset_name && <span>{ad.adset_name}</span>}
          </div>
          <h4>{creative.title || ad.name || "Untitled Meta ad"}</h4>
          <p>{creative.body || "No body copy returned from Meta creative."}</p>
        </div>
        <div className="cockpit-ad-metrics">
          <strong>{fmtInr(m.spend_inr, 0)}</strong>
          <span>{compact(m.impressions)} imps</span>
          <span>{compact(m.clicks)} clicks</span>
          <span>{pct(m.ctr)} CTR</span>
        </div>
      </button>
      {open && (
        <div className="cockpit-detail">
          <MetricTile label="CTR" value={pct(m.ctr)} />
          <MetricTile label="CPC" value={fmtInr(m.cpc_inr, 2)} />
          <MetricTile label="CPM" value={fmtInr(m.cpm_inr, 2)} />
          <MetricTile label="Purchases" value={String(m.purchases ?? 0)} />
          <MetricTile label="ROAS" value={m.roas != null ? `${m.roas.toFixed(2)}x` : "—"} />
          <MetricTile label="Adset Budget" value={fmtInr(ad.adset_daily_budget_inr, 0)} />
          <a href={ad.ads_manager_url || META_ADS_URL} target="_blank" rel="noopener noreferrer">
            Open ad in Meta
          </a>
        </div>
      )}
    </div>
  );
}

export function AdsetPanel({ adset }: { adset: CampaignAdset }) {
  const [open, setOpen] = useState(false);
  const status = adset.effective_status || adset.status;
  return (
    <section className="cockpit-adset">
      <button type="button" className="cockpit-adset-head" onClick={() => setOpen((v) => !v)}>
        <div>
          <span className={`cockpit-status ${statusClass(status)}`}>{status || "UNKNOWN"}</span>
          <h3>{adset.name || adset.adset_id}</h3>
          <p>{adset.stage || "learning"} · {adset.active_ad_count ?? 0}/{adset.ad_count ?? 0} ads active</p>
        </div>
        <div className="cockpit-adset-score">
          <strong>{fmtInr(adset.spend_inr, 0)}</strong>
          <span>{adset.roas != null ? `${adset.roas.toFixed(2)}x ROAS` : "ROAS —"}</span>
        </div>
      </button>
      <div className="cockpit-mini-grid">
        <MetricTile label="Budget" value={fmtInr(adset.daily_budget_inr, 0)} />
        <MetricTile label="CTR" value={pct(adset.ctr)} />
        <MetricTile label="CPC" value={fmtInr(adset.cpc_inr, 2)} />
        <MetricTile label="Purchases" value={String(adset.purchases ?? 0)} />
      </div>
      {open && (
        <div className="cockpit-ad-list">
          {(adset.ads || []).length ? (
            (adset.ads || []).map((ad) => <AdRow key={ad.id} ad={ad} />)
          ) : (
            <div className="cockpit-empty">No ads returned for this adset.</div>
          )}
          <a className="cockpit-meta-link" href={adset.ads_manager_url || META_ADS_URL} target="_blank" rel="noopener noreferrer">
            Open adset in Meta Ads Manager
          </a>
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [data, setData] = useState<CampaignDashboard | null>(null);
  const [automation, setAutomation] = useState<AutomationPayload | null>(null);
  const [activeTab, setActiveTab] = useState<DashboardTab>("command");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(() => new Date());

  const load = useCallback(async () => {
    setError("");
    try {
      const automationBody = {
        started_at_utc: "2026-05-11T15:29:23+00:00",
        not_before_utc: "2026-05-17T15:29:23+00:00",
        interval_days: 6,
        target_roas: 4,
        date_preset: "last_7d",
        min_spend_inr: 500,
        total_daily_budget_inr: 2500,
        max_new_ads_per_cycle: 3,
      };
      const [campaign, machine] = await Promise.all([
        jfetch<CampaignDashboard>("/api/meta/campaign-dashboard"),
        jfetch<AutomationPayload>("/api/automation/ad-machine-tick", {
          method: "POST",
          body: JSON.stringify(automationBody),
        }).catch(() => null),
      ]);
      setData(campaign);
      setAutomation(machine);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 3 * 60 * 1000);
    return () => clearInterval(id);
  }, [load]);

  const totals = data?.totals || {};
  const ads = data?.ads || [];
  const brainActions = data?.brain?.recommended_actions || [];

  return (
    <div className="cockpit-root">
      <header className="cockpit-hero">
        <div>
          <span className="cockpit-kicker">WEARTH Meta Command</span>
          <h1>Founder Ad Cockpit</h1>
          <p>ad command centre · {data?.campaign?.name || "Current live campaign"} · {data?.date_preset || "last_7d"}</p>
        </div>
        <div className="cockpit-hero-actions">
          <button type="button" onClick={load}>{loading ? "Loading..." : "Refresh"}</button>
          <a href={META_ADS_URL} target="_blank" rel="noopener noreferrer">Open Meta</a>
        </div>
      </header>

      {error && <div className="cockpit-error">Fetch error: {error}</div>}

      <nav className="cockpit-tabs">
        <button className={activeTab === "command" ? "active" : ""} onClick={() => setActiveTab("command")}>Campaign</button>
        <button className={activeTab === "video" ? "active" : ""} onClick={() => setActiveTab("video")}>Video Brain</button>
        <button className={activeTab === "image" ? "active" : ""} onClick={() => setActiveTab("image")}>Image Brain</button>
      </nav>

      {activeTab === "command" ? (
        <>
          <section className="cockpit-overview">
            <MetricTile label="Live Ads" value={String(totals.active_ads ?? ads.length)} tone="gold" />
            <MetricTile label="Spend Across Ads" value={fmtInr(totals.spend_inr, 0)} />
            <MetricTile label="Clicks" value={compact(totals.clicks)} />
            <MetricTile label="CTR" value={pct(totals.ctr)} />
            <MetricTile label="CPC" value={fmtInr(totals.cpc_inr, 2)} />
            <MetricTile label="Purchases" value={String(totals.purchases ?? 0)} />
          </section>

          <section className="cockpit-machine">
            <div>
              <span className="cockpit-kicker">Automation Remote</span>
              <h2>{automation?.route?.action || "Safe ad machine router"}</h2>
              <p>{automation?.route?.reason || data?.brain?.summary || "Reading Meta and waiting for enough signal."}</p>
            </div>
            <div className="cockpit-machine-grid">
              <MetricTile label="State" value={automation?.eligible_to_act ? "Ready" : "Observing"} />
              <MetricTile label="Next fire" value={automation?.sleep_window?.not_before_utc ? new Date(automation.sleep_window.not_before_utc).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" }) : "—"} />
              <MetricTile label="Budget guard" value={fmtInr(automation?.budget_guardrails?.planned_total_daily_budget_inr, 0)} />
              <MetricTile label="New ads/cycle" value={String(automation?.budget_guardrails?.max_new_ads_per_cycle ?? 3)} />
            </div>
          </section>

          <section className="cockpit-section">
            <div className="cockpit-section-head">
              <div>
                <span className="cockpit-kicker">Current Campaign</span>
                <h2>Live Ad Capsules</h2>
              </div>
              <span>{ads.length} ads · click any capsule for creative, adset, and metric detail</span>
            </div>
            <div className="cockpit-ad-capsules">
              {ads.length ? (
                ads.map((ad) => <AdRow key={ad.id} ad={ad} />)
              ) : (
                <div className="cockpit-empty">No ads returned from Meta yet.</div>
              )}
            </div>
          </section>

          <section className="cockpit-section">
            <div className="cockpit-section-head">
              <div>
                <span className="cockpit-kicker">Brain Recommendations</span>
                <h2>What The Machine Sees</h2>
              </div>
            </div>
            <div className="cockpit-actions">
              {brainActions.slice(0, 6).map((action, idx) => (
                <div className="cockpit-action" key={`${action.action_type}-${idx}`}>
                  <span>{action.priority || "watch"}</span>
                  <strong>{action.action_type || "hold"}</strong>
                  <p>{action.reason || "No reason returned."}</p>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <section className="cockpit-brain">
          <span className="cockpit-kicker">{activeTab === "video" ? "Video Creative Brain" : "Image Creative Brain"}</span>
          <h2>{activeTab === "video" ? "Production and iteration console" : "Source-first image rescue console"}</h2>
          <p>
            The backend brain exists. Next UI phase adds raw upload, Drive picker, iteration timeline,
            parent judge score, approved output preview, and gated push-live controls.
          </p>
          <div className="cockpit-roadmap">
            <span>Upload</span>
            <span>Diagnose</span>
            <span>Repair</span>
            <span>Judge</span>
            <span>Launch gate</span>
          </div>
        </section>
      )}

      <footer className="cockpit-footer">
        Last updated {updatedAt.toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" })}
      </footer>
    </div>
  );
}
