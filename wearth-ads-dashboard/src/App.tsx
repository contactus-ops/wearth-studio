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
    metaVideoThumb || metaLive?.thumbnail_url || driveThumb || "";

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

export default function App() {
  const [pending, setPending] = useState<PendingAd[]>([]);
  const [live, setLive] = useState<LivePayload | null>(null);
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
      const [p, l] = await Promise.all([
        jfetch<{ ads: PendingAd[] }>("/api/ads/pending"),
        jfetch<LivePayload>("/api/meta/adsets-live"),
      ]);
      setPending(p.ads ?? []);
      setLive(l);
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
                  <div className="metrics-grid">
                    <div className="metric">
                      <div className="metric-val">{fmtInr(a.spend)}</div>
                      <div className="metric-label">7d spend</div>
                    </div>
                    <div className="metric">
                      <div className="metric-val">{a.clicks ?? 0}</div>
                      <div className="metric-label">Clicks</div>
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
                    <div className="metric">
                      <div className="metric-val">{a.impressions ?? 0}</div>
                      <div className="metric-label">Impressions</div>
                    </div>
                  </div>
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
