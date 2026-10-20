# Ad vertical taxonomies

Fetched 2026-10-05. These are the public category trees behind Google Ads, Google Merchant, IAB, and TikTok ads. Meta’s interest tree is not in this folder: the browse API needs an ad-account token, and there is no public CSV.

## Google Ads audience segments

Start page: <https://support.google.com/google-ads/answer/2497941?hl=en>

The page says “download this CSV” three times. The files are on `storage.googleapis.com` and are a channel-availability view (Display, Gmail, Discovery, Search, Shopping, Video), smaller than the API tables.

| File | What it is | Rows |
|---|---|---|
| [google-ads/help-affinity-with-channels.csv](google-ads/help-affinity-with-channels.csv) | Help-page affinity list | 154 |
| [google-ads/help-in-market-with-channels.csv](google-ads/help-in-market-with-channels.csv) | Help-page in-market list | 779 |
| [google-ads/help-detailed-demographics-with-channels.csv](google-ads/help-detailed-demographics-with-channels.csv) | Help-page detailed demographics | 34 |

## Google Ads API tables

Index: <https://developers.google.com/google-ads/api/data/codes-formats> and <https://developers.google.com/google-ads/api/data/topics>

Downloaded from `https://developers.google.com/static/google-ads/api/data/tables/`.

| File | Tree | Rows | Shape |
|---|---|---|---|
| [affinity-categories.csv](google-ads/affinity-categories.csv) | Affinity (passion, habit) | 258 | 15 roots, depth 1–4 |
| [in-market-categories.csv](google-ads/in-market-categories.csv) | In-market (about to buy) | 954 | 26 roots, depth 1–7 |
| [life-events.csv](google-ads/life-events.csv) | Life events | 40 | 11 roots, depth 1–3 |
| [extended-demographics.csv](google-ads/extended-demographics.csv) | Detailed demographics | 25 | 5 roots, depth 2–3 |
| [verticals.csv](google-ads/verticals.csv) | Content topics (the “verticals” file) | 2,558 | 26 roots, depth 1–8 |
| [productsservices.csv](google-ads/productsservices.csv) | Products and services | 3,180 | 22 roots, depth 1–7 |
| [mobileappcategories.csv](google-ads/mobileappcategories.csv) | App-store categories | 148 | one root, depth 1–4 |

Columns are criterion id, parent id, and a `/`-separated path. The help-page affinity file (154) and the API affinity file (258) are the same idea at two dates. The API file is the fuller tree.

## Google Merchant product taxonomy

<https://support.google.com/merchants/answer/6324436>

[google-merchant/taxonomy-with-ids.en-US.txt](google-merchant/taxonomy-with-ids.en-US.txt) — version header `2021-09-21`, 5,595 categories, 22 roots, path separator ` > `, max depth 7. Identity is a numeric id. The path is the display form.

## IAB Tech Lab

Repo: <https://github.com/InteractiveAdvertisingBureau/Taxonomies>

| File | Tree |
|---|---|
| [iab/content-taxonomy-3.1.tsv](iab/content-taxonomy-3.1.tsv) | What the page is about. 673 nodes, 62 roots, max tier 4. |
| [iab/content-taxonomy-3.0-descriptive-vectors.tsv](iab/content-taxonomy-3.0-descriptive-vectors.tsv) | Orthogonal vectors: environment, purpose, source, form factor, brand risk, language, geo. 47 nodes. |
| [iab/ad-product-taxonomy-2.0.tsv](iab/ad-product-taxonomy-2.0.tsv) | What is being advertised. 583 nodes, 46 roots, max tier 3. IAB cut this from 5 tiers to 3. |

## TikTok ads industry

No official CSV on the public web. The Creative Center / ads industry list used in the wild is the two-level tree in [tiktok/tiktok-ads-industry-code.json](tiktok/tiktok-ads-industry-code.json) (and the Chinese names in `tiktok-ads-industry-code-zh.json`), from <https://github.com/TikHub/TikTok-Ads-Industry-Code>. 21 industries, 237 sub-industries. 19 of the 21 parents have an `Other …` child. TikTok Business API account creation asks for the second-level id, not the parent.

A separate, deeper product-category tree exists for TikTok Shop listings. That is a catalog taxonomy, not the ads vertical, and it is not stored here.

## Meta

Design only, no file. Detailed targeting is several classes (`interests`, `behaviors`, `life_events`, `industries`, `family_statuses`, …), each a flat list with a parent key and a `path`, plus audience-size bounds. Special Ad Categories (`HOUSING`, `EMPLOYMENT`, `FINANCIAL_PRODUCTS_SERVICES`, `ISSUES_ELECTIONS_POLITICS`) are a policy flag on the campaign. They turn branches off. They are not another level of the interest tree. Docs: <https://developers.facebook.com/docs/marketing-api/audiences/reference/detailed-targeting/> and <https://developers.facebook.com/docs/marketing-api/audiences/special-ad-category/>.
