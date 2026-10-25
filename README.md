# IM Research Jobs Tracker

Checks the careers websites and postdoc job boards of the 50 US medical schools with the most NIH funding for Internal Medicine (BRIMR 2025 ranking), plus Harvard, Mayo Clinic and Beth Israel Deaconess, once a day. It keeps research-only roles (postdoctoral, research fellow, research associate; clinical research coordinator roles are excluded) first posted within the last 21 days, separates clinical or data research from wet-lab work, flags eligibility problems (citizenship, no visa sponsorship, PhD-only), and shows the results on a web dashboard hosted free on GitHub Pages (anyone with the link can open it; search engines are asked not to index it).

## What it covers

The 50 US medical schools with the most NIH funding for Internal Medicine (BRIMR 2025, `config/brimr_2025_im_top50.txt`), plus Harvard, Mayo Clinic and Beth Israel Deaconess / Beth Israel Lahey Health. For each school the tracker reads the main HR careers site and, where one exists, the postdoc office's own list of openings. "Link only" sources cannot be read automatically (login, bot protection, or a robots.txt rule against automated reading); the dashboard's Sources tab links to them for a manual check.

| Rank | School | Read automatically | Link only |
|---|---|---|---|
| 1 | Vanderbilt | VUMC (Workday), University (Oracle), postdoc office board | |
| 2 | UCSF | Oracle, UC Recruit | |
| 3 | Johns Hopkins | Eightfold | |
| 4 | Columbia | | Staff site (bot protection), academic jobs (PeopleAdmin) |
| 5 | Penn | Workday | Postdoc programs job list |
| 6 | Pittsburgh | | Staff site (login), postdoc job site |
| 7 | WashU | Workday | |
| 8 | Duke | SuccessFactors | |
| 9 | UCLA | Jibe, UC Recruit | |
| 10 | Mount Sinai | Jibe | |
| 11 | NYU Langone | m-cloud | |
| 12 | Yale | Workday, postdoc office board (newest 10 posts) | |
| 13 | UC San Diego | Job list pages, UC Recruit | |
| 14 | CU Anschutz | Taleo | |
| 15 | Stanford | Oracle, postdoc office board | |
| 16 | Northwestern | | PeopleSoft, postdoc office list |
| 17 | Michigan | Job list pages | |
| 18 | Weill Cornell | SuccessFactors | Postdoc office board (refuses automated requests) |
| 19 | University of Washington | Workday | |
| 20 | UChicago | Workday | |
| 21 | UT Southwestern | m-cloud | |
| 22 | Emory | Jibe (includes the faculty and postdoc portal) | |
| 23 | UNC Chapel Hill | | PeopleAdmin |
| 24 | UAB | | Careers site, postdoc office list |
| 25 | UW-Madison | Job sitemap | Postdoc vacancy list |
| 26 | Baylor College of Medicine | | SuccessFactors |
| 27 | OHSU | | iCIMS postdoc portal and main portal (refuse automated requests) |
| 28 | Indiana University | | PeopleAdmin |
| 29 | Boston University | SilkRoad | |
| 30 | Wake Forest | m-cloud (Winston-Salem only) | |
| 31 | South Florida | | Postdoc list (spreadsheet) |
| 32 | Rutgers | | PeopleAdmin |
| 33 | Case Western / Cleveland Clinic | Cleveland Clinic (Workday), University Hospitals (m-cloud) | Case Western |
| 34 | Utah | | Careers site |
| 35 | Albert Einstein | Jibe | |
| 36 | Ohio State | Workday | |
| 37 | Minnesota | | PeopleSoft |
| 38 | Miami | Workday | |
| 39 | UT Austin (Dell) | Workday | |
| 40 | USC | Workday | |
| 41 | Virginia | | Careers site |
| 42 | Florida | PageUp job list (titles and departments only; job pages refuse automated requests) | |
| 43 | Medical College of Wisconsin | Workday | |
| 44 | UMass Chan | | iCIMS (refuses automated requests) |
| 45 | Maryland, Baltimore | Oracle (faculty and postdoc site, staff site) | |
| 46 | Tulane | Oracle (academic site, staff site) | |
| 47 | Rochester | Workday, postdoc office list | |
| 48 | Iowa | Postdoc openings (Carver College of Medicine) | |
| 49 | UC Davis | UC Recruit | |
| 50 | Louisville | Workday | |
| added | Harvard | Harvard careers sitemap, Mass General Brigham (Workday) | |
| added | Mayo Clinic | Oracle | |
| added | Beth Israel Deaconess / Beth Israel Lahey Health | BILH careers site (covers BIDMC) | Joslin Diabetes Center (iCIMS) |
| added | Houston Methodist | Postdoctoral fellow job category (careers site) | |
| added | Baylor Scott & White | Phenom careers site | |
| added | Brown University | Workday (staff site) | |
| added | KU Medical Center | Workday | |
| added | Minneapolis Heart Institute Foundation | Careers page (titles only; job pages are on ADP) | |
| added | MUSC | Workday | |

Harvard, Mayo Clinic and Beth Israel Deaconess / Beth Israel Lahey Health are added by choice: BRIMR ranks Harvard's teaching hospitals separately from the medical school, and Mayo's NIH funding is not coded by department. Six more (Houston Methodist, Baylor Scott & White, Brown, KU Medical Center, Minneapolis Heart Institute Foundation, MUSC) were added because a LinkedIn sample showed foreign medical graduates currently holding research fellow or postdoc posts there.

Known gaps: postdoc posts that departments advertise only on Interfolio, lab websites or by email are not on these boards. Some iCIMS portals and postdoc boards show no posting date; such postings are shown for up to 21 days after the tracker first sees them (so on the first day after a new source is added, older undated postings can appear once and then drop off).

## How it decides

1. **Title filter**: keeps research-role titles, drops nursing, faculty, technician, manager and similar titles (`config/profile.yaml`).
2. **Keyword rules**: reads the department and description for Internal Medicine division, wet-lab terms (mice, cell culture, qPCR, flow cytometry, cryo-EM and similar), clinical terms (patients, IRB, cohort, registry, R) and eligibility flags.
3. **Claude classifier** (only if you add an API key): Claude Haiku reads each new posting once and gives a verdict with a short reason. It replaces the keyword verdict; the keyword signals stay visible on each card.
4. **Second opinion, decisive**: every posting Haiku marks "Match" or "Needs a look" is re-checked once by Claude Sonnet, which is told to make the call rather than leave it open. Each verdict carries a confidence (high, medium, low), a "Verify" line naming the one fact to confirm before applying, and a skills-fit check against the profile. Cards show "re-checked by Claude Sonnet", with Haiku's first verdict under "Excerpt and rule signals". Limit: 80 re-checks per run. Remove `review_model` in `config/profile.yaml` to switch it off.
5. **Web checks for postings still undecided** (Claude Sonnet with Anthropic's web search and web fetch tools; the fetch tool honours robots.txt). Each posting is checked once.
   - **Find the posting**: when the employer's page gave only a title, Sonnet searches for the same posting (the employer's own pages first, then job-board copies), accepts a copy only if it shows the same job ID, or the same title, institution and department, and classifies from the copy's text. The card says whether the copy was primary or secondary and how it was matched, with a link. Postings with no readable copy go to the **Title only** tab. Limit: 15 per run.
   - **Lab lookup**: when the posting names a PI or lab but not the work, Sonnet looks up the lab's pages and recent papers (institution pages, PubMed, NIH RePORTER) to tell wet-lab from clinical or dry work. The card shows "Lab check" with the PI, a one-line lab summary and links to the pages used. Only links that came back from the search are kept. Limit: 15 per run.
   - Cost: web search is USD 10 per 1,000 searches (up to 4 per posting) plus tokens; web fetch costs tokens only. Remove `lookup_model` to switch both off.

Dashboard tabs: **Matches** (most certain first, then soonest deadline; a red badge shows postings closing within 7 days), **Stretch** (dry IM research, but a required skill such as omics or machine learning is not in the profile), **Needs a look** (postings whose text was read but the AI could not decide, or matched only with low confidence), **Title only** (only the title could be read and no readable copy was found), **Below level** (jobs whose minimum is a high-school or bachelor's degree, such as research assistant, coordinator, outreach or University of California "Staff Research Associate" jobs; the level is judged from the required degree, not the title, because "Research Associate" is a postdoctoral or higher title at many schools), **Other departments** (clinical research outside IM, such as epidemiology), **Excluded** (kept visible so you can audit mistakes), and **Sources** (which sites worked today).

Neither the rules nor the AI are perfect. Treat "Matches" as a shortlist and read each posting before applying.

## Setup (about 20 minutes, one time)

### 1. Create a GitHub account and repository
1. Sign up at github.com (free).
2. Click **New repository**. Name it, for example, `im-research-jobs`. Choose **Public** (GitHub Pages on a free account needs a public repository; see Security below for why this is safe). Click **Create repository**.

### 2. Upload the files
1. On the new repository page, click **uploading an existing file**.
2. Drag in everything from the unzipped folder **except** the `.github` folder (some computers hide folders that start with a dot). Click **Commit changes**.
3. Add the workflow file by hand: click **Add file > Create new file**, type the name `.github/workflows/daily.yml`, paste the contents of that file from the zip, and click **Commit changes**.

### 3. Turn on the dashboard
1. Repository **Settings > Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.

### 4. Add the Claude API key (optional, paid)
1. Go to platform.claude.com, sign in, and add a small amount of prepaid credit.
2. **Settings > Workspaces**: create a workspace called `job-tracker`, open it, click **Spend limits**, and set a monthly cap (for example USD 5). Spend limits cannot be set on the Default workspace, which is why a separate one is used.
3. Create an API key inside that workspace. Copy it once.
4. In GitHub: repository **Settings > Secrets and variables > Actions > New repository secret**. Name: `ANTHROPIC_API_KEY`. Value: the key. Save.

Expected cost (estimate): the classifier uses Claude Haiku 5.5, priced at USD 0.10 per million input tokens and USD 0.50 per million output tokens for prompts under 100,000 tokens. One posting is roughly 2,500 input and 200 output tokens, so about USD 0.0004 per posting. The first run may classify up to 150 postings (under USD 0.10); later days only new postings are classified. Check the price page yourself before relying on this.

### 5. First run
1. Repository **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Select **Daily job scan > Run workflow**.
3. The first run reads many postings and can take 30 to 90 minutes. When it finishes, the dashboard address appears in **Settings > Pages** (it looks like `https://YOURNAME.github.io/im-research-jobs/`).

After that it runs by itself every day at 06:00 IST.

## Security: what protects your key and account

- **The key is never in the code.** It lives only in GitHub's encrypted Actions secrets. GitHub hides it from logs, and the code never prints request headers.
- **Strangers cannot use your secret.** The workflow has no pull-request trigger, so code proposed by other people never runs with your key. Anyone can copy (fork) a public repository, but forks do not receive your secrets.
- **Spend cap.** The separate Anthropic workspace with a monthly spend limit bounds the worst case, even if the key ever leaked. If you suspect a leak, delete the key in the Console and create a new one.
- **Least privilege.** The workflow starts with no permissions; the scan job may only write repository files, and the deploy job may only publish Pages.
- **Few dependencies.** Three Python packages, pinned to exact versions, and only GitHub's own official actions. The dashboard loads no outside scripts and a Content-Security-Policy blocks them.
- **Scraped text cannot run in the dashboard.** All job text is displayed as plain text, never as HTML.
- **Nothing personal is published.** The public repository and dashboard contain only public job postings and a short anonymous profile (`config/profile.yaml`). Do not add names, emails, phone numbers or a CV to the repository.
- **Polite to the universities.** One run per day, at least 1 second between requests to the same site (longer if the site asks for it), a cap per site, and robots.txt is respected. If a site's robots.txt forbids a page, that source is skipped and shown as "blocked".

## Changing things

- **Search words, title rules, divisions, wet-lab terms, profile summary**: `config/profile.yaml`.
- **Add or pause a school**: `config/sources.yaml` (set `enabled: false` to pause).
- **Run time**: the `cron` line in `.github/workflows/daily.yml` (UTC).

## Limits you should know

- Career sites change. If a site redesigns, its source shows an error on the Sources tab until the connector is updated. The rest keep working.
- Some sites may block requests from GitHub's servers even though they work in a browser. The first live run will show which ones.
- Scheduled runs can start late when GitHub is busy, and GitHub pauses schedules in repositories with no activity for 60 days. The daily data commit counts as activity in normal use; if the schedule ever stops, open the Actions tab and re-enable it.
- "Applied" and "Hide" marks are stored only in the browser you used.

## Running tests locally (optional)

```
pip install -r requirements.txt pytest==9.1.1
python -m pytest -q
```
The tests use trimmed copies of real postings captured on 23 Oct 2026.
