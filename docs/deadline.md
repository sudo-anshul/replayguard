# First Commit deadline and requirements

**Current cutoff: September 20, 2026, 20:00 IST (14:30 UTC).** A [read-only, TLS-verified official API check at September 20, 07:05:26 UTC](publication/deadline-current-20260920.json) returned `end_date: "2026-09-20T14:30:00Z"`, with configuration updated at `2026-09-20T04:57:05.393246Z`. Submit before this cutoff. This supersedes the earlier 09:00 IST guidance and resolves the previously recorded API/countdown time mismatch. The dated observations and source evidence below remain unchanged as history.

## Historical research and refreshes

Fetched 2026-09-18 18:38–18:42 UTC (September 19 in India). Evidence manifest recorded **2026-09-18 18:42 UTC**. All HTTP sources were fetched using HTTPS with TLS verification. Firecrawl was attempted but had insufficient credits; no upgrade was made. Read-only browser inspection confirmed the rendered countdown and signed-out submission state.

**Refresh: September 19, 2026, 04:12 UTC.** A read-only, TLS-verified fetch confirmed that the submission API still returns `end_date: "2026-09-20T03:30:00Z"` (**September 20, 09:00 IST**). The refreshed overview HTML exposed a start time but no end time; it does not resolve the earlier countdown/API discrepancy. [Refresh timestamp and response fingerprints](deadline-refresh-20260919.json). No AWS API or submission action was used.

## Historical cutoff comparison — superseded by the current configuration above

**Use September 20, 2026, 09:00 IST (03:30 UTC) as the earlier operational boundary. Finish and submit well before it. The exact organizer-approved cutoff remains unresolved because the official sources disagree. Do not assume midnight.**

| Official source | Observed value | Meaning |
| --- | --- | --- |
| [Public hackathon API used by the site](https://wemakedevs-server.onrender.com/hackathons/first-commit) | `end_date: "2026-09-20T03:30:00Z"` | 09:00 IST, September 20, 2026 |
| [Submission page](https://www.wemakedevs.org/aws/first-commit/submit), [published JS bundle](https://www.wemakedevs.org/_next/static/immutable/chunks/23nphn7_7clzr.js) | Compares `new Date(M.end_date).getTime()` with `Date.now()` and returns **“Submissions are closed”** after the end | The submission UI gates on the API's earlier time. Server enforcement was not tested; no form was submitted. |
| [Event overview](https://www.wemakedevs.org/aws/first-commit), visible countdown | DOM `<time datetime="2026-09-20T14:30:00Z">` | 20:00 IST, September 20, 2026, **11 hours later** |
| [Official schedule](https://www.wemakedevs.org/aws/first-commit/schedule) | September 20: “Last day to submit your project online, demo video included.” Then: “The hours are being finalised: the kickoff call, mentor sessions, and the deadline the clock stops on.” | No final hour/timezone is published in the schedule prose. |

The homepage countdown is hardcoded in `FIRST_COMMIT_WINDOW`; its date is independent of the API. The submit form requires sign-in, and the signed-out UI does not expose an exact deadline. No organizer was contacted, no account created, and no submission made.

Local evidence:

- `official-hackathon-api.json`: captured API response; its `updated_at` is `2026-09-05T13:16:00.284352Z`.
- `assets/23nphn7_7clzr.js`, **line 1**: `let eC=p<=Date.now(); ... b=new Date(M.end_date).getTime() ... let ez=b<Date.now()`; `eD=eC&&!ez&&eT`; later `if(ez)` returns heading `"Submissions are closed"`.
- `assets/0avcoity_epag.js`, **line 1**: `FIRST_COMMIT_WINDOW` is `{start:"2026-09-17T02:30:00Z",end:"2026-09-20T14:30:00Z"}`; countdown emits this into `time.dateTime`.
- `assets/32u9w5ftwk842.js`, **line 1**: `getHackathon` fetches `/hackathons/${encodeURIComponent(e)}`.
- `assets/0c0uw9a_4t67r.js`, **line 1**: public API base is `https://wemakedevs-server.onrender.com`.
- `official-schedule.txt`, **lines 73–80**: September 20 and the hours-being-finalised statement.
- `deadline-evidence.json`: concise structured findings and exact code excerpts.
- `manifest.json`: source URLs, collection time, and SHA-256 hashes.

## Mandatory submission requirements

Source: [official tour rules](https://www.wemakedevs.org/aws/rules), last updated **September 16, 2026**, and [First Commit rules](https://www.wemakedevs.org/aws/first-commit/rules).

- **Public repository**, **demo video**, and a **short writeup covering the problem, the build, and where AWS fits**.
- Video **must be on YouTube**, **public or unlisted**, and **under three minutes**. Check its link in a signed-out browser. Rules initially say “up to three minutes” but immediately specify “under three minutes”; target 2:40–2:50 to satisfy the stricter wording.
- Video **must show AWS use**. Naming AWS only in the writeup is insufficient. Judges see the recorded submission: there is no live demo/call, and features absent from video do not count.
- **Ship It** requires a live deployment on AWS with a URL; architecture and cost decisions are scored. The overall API form's “Live demo or deployment” field is optional because it also serves the local Build It track.
- One submission per team, on the [event submission form](https://www.wemakedevs.org/aws/first-commit/submit), before its deadline. Deadlines are strict.
- Build a **new project during the event**. Existing projects do not qualify, even if rewritten. Repository history must match event dates. Libraries, frameworks, public APIs, boilerplate and starter templates are allowed; credit and compatible licensing are required.
- **AI coding tools are allowed; list them in the writeup**. Disclose Codex and any other tools actually used.

The live API form requires: **Project title** (maximum 120 characters), **Description**, **Repository**, and **Demo video**. **Live demo or deployment** is optional at form level, but needed for Ship It.

## Eligibility and account requirements

- University student **in India**, **18 or older**.
- Individual **WeMakeDevs account**, tour registration, and First Commit check-in.
- **AWS Builder Center profile with university enrollment verified**, using **SheerID**. Student verification elsewhere alone is not necessarily the required verification.
- Solo or teams of **1–4**. Every member independently qualifies and registers; one team per person for this hackathon.
- Open SheerID cases do not prevent judging/prize consideration while resolved. Verified status is needed for Builder Center rewards and the separate fast-track interview.
- Fast-track interview category additionally targets graduation years **2027/2028** and has separate terms; it is not required to enter the hackathon or win a project prize.
- No particular AI or additional AWS service is mandated for this project. Lambda/SQS/DynamoDB on AWS fits **Ship It**. AWS use must be demonstrated, and cost decisions matter.

## Relevant judging emphasis

[First Commit overview](https://www.wemakedevs.org/aws/first-commit): idea/impact, AWS use, learning, working execution, recorded demo. The overview explicitly says **“A small problem solved well beats a big one solved vaguely”** and **“One feature that runs beats five that almost do.”** ReplayGuard's focused failure/repair loop fits this direction.

AWS Builder Center blogging is optional for a separate “Top 5 blogs” prize. Registration, student verification, YouTube upload, and hackathon submission have not been verified as completed in the user's accounts during this research.
