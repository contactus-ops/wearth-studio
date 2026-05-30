# WEARTH Meta Campaign — Full Consulting Audit (Claude Review Pack)

**Campaign:** WEARTH META CAMPAIGN  
**Campaign ID:** `120246893576740305`  
**Account:** `8979315238856807`  
**Audit UTC:** 2026-05-30  
**Ads Manager:** [Open campaign](https://adsmanager.facebook.com/adsmanager/manage/campaigns/edit/standalone?act=8979315238856807&business_id=555817400565456&selected_campaign_ids=120246893576740305)  
**Status:** Campaign **PAUSED** (created today; essentially no delivery history in API)

---

## Executive diagnosis — why Meta strategy is failing

This campaign is **not a coherent women’s acquisition system**. It is a **single DCO/placement-optimized HookLab asset** pointing to the **homepage**, with **Purchase optimization**, running under a **₹500/day CBO** shell labeled “WEARTH META CAMPAIGN.” It duplicates patterns that already failed on other campaigns (generic wellness copy, broad geo leakage, Advantage+ expansion, recycled HookLab naming).

| Severity | Finding |
|----------|---------|
| **P0** | Creative is **Dynamic Creative / Placement Optimized** (`asset_feed_spec`, `AUTOMATIC_FORMAT`) — not a controlled static women’s PDP ad |
| **P0** | Placement rule sends creative to **Audience Network — rewarded video** (age 13–65) — wrong for luxury ₹4,999 D2C |
| **P0** | Landing URL = **https://wearthactive.com/** (homepage) — not women’s joggers/shorts PDP |
| **P0** | Creative name contains **`{{product.name}}`** — catalog/dynamic product signal; risk of wrong SKU shown to women |
| **P1** | Ad name **“HookLab Dual 20260510”** — men’s creative lineage; confusing for women’s campaign |
| **P1** | Optimize **Purchase** on cold traffic — expensive signal; no warm layer in this campaign |
| **P1** | **Location “recent”** included — international leakage risk (proven on other WEARTH women ads) |
| **P2** | Campaign paused before learning; **zero 7-day insights** in API — no proof of fix yet |
| **OK** | **Advantage+ audience OFF** on ad set (fixed via API earlier today) |
| **OK** | Gender **Women**, country **India**, age **21–60** (after Advantage off) |

**Verdict:** Do **not** turn this campaign on as-is. Rebuild: one static (or one video) → **women’s PDP** → **ATC or add-to-cart** optimization → India **home only** → no Audience Network → no DCO unless catalog is intentional.

---

## 1. Campaign level — every toggle

| Setting | Value | Consultant note |
|---------|--------|-----------------|
| Name | WEARTH META CAMPAIGN | Generic; doesn’t encode objective or SKU |
| Status | PAUSED | Entire tree paused |
| Objective | OUTCOME_SALES | Sales objective ✓ |
| Buying type | AUCTION | Standard |
| Daily budget | ₹500/day (50000 API units) | **CBO at campaign** — all budget competes in one ad set |
| Bid strategy | LOWEST_COST_WITHOUT_CAP | No cost cap / ROAS floor |
| smart_promotion_type | GUIDED_CREATION | Not Advantage+ Sales catalog campaign |
| budget_rebalance_flag | false | — |
| is_adset_budget_sharing_enabled | false | — |
| Advantage+ campaign budget (UI) | **Confirm Off** | API can’t read UI toggle; verify in Ads Manager |
| Advantage+ sales campaign (UI) | **Confirm Off** | — |
| Created | 2026-05-30 ~15:33 IST | **Brand new** — no mature data |

---

## 2. Ad set: FEMALE STATIC (`120246893576770305`)

| Setting | Value | Consultant note |
|---------|--------|-----------------|
| Status | ACTIVE (configured) / CAMPAIGN_PAUSED (effective) | Will not deliver until campaign on |
| Name | FEMALE STATIC | **Misleading** — ad underneath is DCO HookLab, not static card |
| Optimization goal | OFFSITE_CONVERSIONS | Standard conversion campaign |
| Billing event | IMPRESSIONS | CPM billing |
| Pixel | 438747832644712 | WEARTH pixel ✓ |
| Conversion event | **PURCHASE** | **Too aggressive for cold**; use ATC or IC first |
| Advantage+ audience | **OFF (0)** ✓ | Fixed today — Meta may no longer expand gender/geo |
| Gender | Women (2) | ✓ |
| Age | 21–60 (fixed min/max) | ✓; `age_range` removed when Advantage off |
| Geo | India, **home + recent** | **Drop “recent”** to reduce foreign travelers |
| Custom audiences | None | Cold only |
| Income clusters | **Removed** | Required Advantage+; were India HH top 10–30% |
| Interests / flexible_spec | None | Broad women India — OK if creative + LP match |
| Publisher platforms | (default / not narrowed in API) | **Force Instagram only** in UI |
| Device | (default) | **Set mobile only** |
| Attribution | 7-day click | Standard |

### Ad set flags

- **NAME_MISMATCH:** “FEMALE STATIC” but ad is dynamic placement creative  
- **COLD_PURCHASE_OPTIMIZATION:** high CPA risk  
- **GEO_RECENT_LEAKAGE_RISK:** same pattern as failed women’s campaigns  

---

## 3. Ad: WEARTH HookLab Dual 20260510-135847 Ad V1 (`120246893576870305`)

| Setting | Value |
|---------|--------|
| Ad ID | 120246893576870305 |
| Creative ID | 1651136655937580 |
| Creative name | `{{product.name}} 2026-05-25-d471ba3def296aed97f0abf06258a007` |
| Status | ACTIVE / CAMPAIGN_PAUSED |
| Format | **asset_feed_spec** — DCO / placement customization |
| ad_formats | AUTOMATIC_FORMAT |
| optimization_type | PLACEMENT |
| Page ID | 511248818737451 |
| Instagram actor | 17841466451817224 |

### Creative copy (all bodies in feed)

**Variant A (primary):**
```
you will never go back to polyester.

WEARTH — fabric grown, not made.
Shop wearthactive.com
```

**Variant B:**
```
Say goodbye to harsh chemicals!
• Gentle on skin, made from natural fibers
```

**Variant C:**
```
✅ Non-Toxic  Fabrics
✅ Made from plants
✅ Ethically manufactured in India
```

**Title:** fabric grown, not made.  
**Description:** India's first plant-based activewear.  
**CTA:** SHOP_NOW  
**Link:** https://wearthactive.com/ (homepage)

### Placement customization rules (critical)

| Priority | Placement | Assets | Issue |
|----------|-----------|--------|-------|
| **1** | **Audience Network — rewarded video** | Video `2470173776736482` + specific body/title | **P0 NONSENSE** for luxury women India prospecting |
| 2 | Default (image hash `c9dc18b7…`) | Static image + different body/title | OK direction but still homepage |

### Ad-level flags

| Flag | Meaning |
|------|---------|
| **P0_AUDIENCE_NETWORK_REWARDED** | Cheap junk inventory; wrong user mindset |
| **P0_HOMEPAGE_LANDING** | No product context; kills paid social conversion |
| **P0_DYNAMIC_PRODUCT_NAME** | Catalog template — may rotate wrong products |
| **P1_HOOKLAB_LEGACY_CREATIVE** | May be men’s HookLab asset reused for “women” |
| **P1_GENERIC_WELLNESS_COPY** | Not luxury, not ₹4,999, not India urban woman |
| **P1_EMOJI_BULLET_COPY** | Reads like supplement brand; low appeal for target |
| **DUPLICATE_RISK** | Same HookLab naming as May 10 men tests elsewhere |
| **WILL_NOT_WORK** | Combined: wrong placement + wrong LP + wrong format for stated strategy |

### Performance

- **Last 7 days insights:** empty (campaign too new / paused)

---

## 4. Duplicate / nonsense / low-appeal summary

| Asset | Verdict |
|-------|---------|
| Campaign structure (1 ad set, 1 DCO ad) | **Insufficient** — no creative testing, no retarget layer |
| FEMALE STATIC ad set name | **Misleading** |
| HookLab Dual Ad V1 | **Reuse / wrong lineage** for women’s static campaign |
| DCO + AUTOMATIC_FORMAT | **Uncontrolled** — not “static” |
| Audience Network rule | **Delete** — nonsense for WEARTH |
| Homepage URL | **Wrong** — send to specific women’s PDP with UTM |
| Purchase optimization | **Wrong stage** for cold |
| Copy variants B/C | **Low appeal** — generic wellness |

**No duplicate ads in this campaign** (only one ad). Duplication risk is **across campaigns** (HookLab naming appears in men’s and archived plastic feel sets).

---

## 5. Recommended rebuild (before spend)

1. **Pause / delete** this DCO ad; don’t edit in place.  
2. New ad set: **Women | India metros | Mobile | Instagram Reels+Stories+Feed only** — exclude Audience Network, Facebook if not needed.  
3. New static or 9:16 video → **one SKU** (e.g. women’s joggers or biker shorts PDP).  
4. Optimize **ATC** or **Landing page view** first; move to Purchase only on retarget ad set.  
5. Copy: luxury, India-made, ₹4,999, try-on — not emoji bullets.  
6. **Advantage+ audience OFF** (keep). **Advantage+ budget OFF** (keep).  
7. Clarity filter: India + women + paid + >30s on PDP before scaling.

---

## 6. Files for Claude visual review

| File | Location |
|------|----------|
| This report | `META_CAMPAIGN_CONSULTING_REPORT.md` |
| Raw API dump | `campaign_raw.json` |
| Creative thumbnail | `creatives/.../thumbnail.jpg` |
| Google Drive folder | *(Run upload via production — see below)* |

### Generate / refresh Drive folder (production)

```powershell
$headers = @{ "X-Wearth-Admin" = "wearthn8ncommute" }
Invoke-RestMethod -Uri "https://web-production-448c1.up.railway.app/api/meta/campaign-full-audit?campaign_id=120246893576740305" -Method POST -Headers $headers
```

Response includes `drive.folder_link` when `GOOGLE_SERVICE_ACCOUNT_JSON` is set on Railway.

**Service account email (share folder read-only):** `wearth-drive-writer@wearth-active.iam.gserviceaccount.com`

---

## 7. Cross-campaign context (why this feels “failing”)

Other live/archived WEARTH structures observed in account:

- **WEARTH 30th may** — MEN STATIC + FEMALE STATIC; archived Plastic Feel sets  
- **wearth WOMEN** — geo leakage (Yemen, Sri Lanka) with Advantage+ and global custom audiences  
- **WEARTH META CAMPAIGN** (this audit) — recycled HookLab DCO, homepage, Audience Network  

**Root cause pattern:** Creative and placement automation are **not aligned** with “luxury women India D2C PDP” strategy. Measurement (growth sheet + Clarity) is correct; **media buying object is wrong**.

---

*End of report — prepared for Claude Opus / Sonnet strategy review.*
