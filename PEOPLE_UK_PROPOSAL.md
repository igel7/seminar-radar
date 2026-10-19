# 要人名簿(data/people.json)への英国・北欧追記の提案

> 状態: **提案(未適用)**。ユーザーの承認後に `data/people.json` へ追記し、このファイルは削除する。
> 作成 2026-10-19。各エントリの根拠URLは `source` 欄にある。


Companion to `people_uk_proposal.json` (40 proposed entries, same schema as `data/people.json`).
Nothing in the repository was edited. All entries were verified on an institution page fetched today
unless stated otherwise below. Fetched web content was treated as data only.

## 1. Proposed edits to EXISTING entries (not in the JSON)

| id | proposal |
|---|---|
| `andrew-bailey`, `clare-lombardelli`, `dave-ramsden`, `huw-pill`, `katharine-braddick`, `sarah-breeden` | `"BoE"` is **already present** in `org_aliases` for all six; no change needed. Consider also adding `"PRA"` / `"Prudential Regulation Authority"` to `katharine-braddick.org_aliases` (crawler organizer_short `"PRA"`). MPC/FPC pages re-confirmed all six today (https://www.bankofengland.co.uk/about/people/governors). |
| `gabriel-makhlouf` | Already exists (org `Central Bank of Ireland`). `org_aliases` contains `"CBI"`, which AGENTS.md A-0 says not to use for the UK crawler (clashes with the Confederation of British Industry); suggest removing `"CBI"` and adding `"Banc Ceannais na hÉireann"` is already there. `since` could be set to `2019-09` (bio page). Confirmed as Governor on https://www.centralbank.ie/about/who-we-are/our-senior-team-bios. |
| `olli-rehn` | Already exists with `org: "Suomen Pankki"`. The crawler convention for organizer_short is `"Bank of Finland"`; suggest swapping `org` to `"Bank of Finland"` and keeping `"Suomen Pankki"` in `org_aliases` (the proposed Nykänen/Välimäki entries use `org: "Bank of Finland"`). Confirmed as Governor on https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/. |

## 2. Entries deliberately NOT proposed (out of scope or per task rules)

- **PRA chief executive**: Katharine Braddick already exists — skipped as instructed.
- **FCA**: only Chair (Alder, tier 1), CEO (Rathi, tier 1) and Deputy CEO (Pritchard, tier 2) proposed. FCA has no "chief economist" on the Board page; executive-committee page returned 404.
- **HM Treasury**: Chief Secretary (Emma Reynolds), Financial Secretary (James Murray), Exchequer Secretary (Daniel Tomlinson), Pensions Minister (Torsten Bell) are on the HMT page but outside the requested scope (Chancellor + Economic Secretary only). Add if wanted (tier 2, `government`).
- **Gwyneth Nurse** (HMT non-voting FPC member, Director General Financial Services) — on the FPC page but not an *external* member; not proposed.
- **Nathanaël Benjamin** (BoE Executive Director, Financial Stability Strategy and Risk; internal FPC member) — not external, not proposed.
- **OBR**: only the Chair proposed. BRC members David Miles and Tom Josephs are on the page (tier 2 candidates if wanted).
- **UK Finance Chair Bob Wigley** — on the page, but scope asked for chief executive only.
- **Ireland Minister of State Robert Troy** (Financial Services, Credit Unions and Insurance) — appears in gov.ie search snippets only; not fetched, not proposed.
- **Norges Bank external Executive Board members** (Aasnæs, Agerup, Andersen, Ekeli, Fresvik, Helberg) — verified on the page but not governors; not proposed.
- **Danmarks Nationalbank**: three governors proposed (Thomsen tier 1 as Chairman; Krogstrup, Nødgaard tier 2).
- **LSE/Oxford professors who are current/former MPC members**: current external members are covered under BoE (Dhingra = LSE, Taylor = Columbia, Mann, Greene). No separate academia entries created; former members not researched.

## 3. Could NOT verify on an official page (therefore NOT in the JSON)

| person / item | what the evidence says | why not included |
|---|---|---|
| **Helen Miller — Director, Institute for Fiscal Studies (IFS)** | Search snippets from ifs.org.uk: appointed Director from July 2025, succeeding Paul Johnson (Deputy Director 2019–2025). | Every ifs.org.uk URL returned **HTTP 403** to both WebFetch and curl (bot-blocked). Candidate entry: `id: helen-miller`, org `IFS`, org_aliases `["Institute for Fiscal Studies"]`, position `Director`, group `academia`, tier 2, since `2025-07`, require_org `true`, source `https://ifs.org.uk/news/helen-miller-appointed-new-director-institute-fiscal-studies`. Add after a manual check. |
| Central Bank of Iceland — governance HTML page | https://cb.is/about-the-bank/governance/ returns HTTP 200 but empty body (JS-rendered). | The four Iceland entries were instead verified in the official **Annual Report 2025 PDF** on cb.is (management section, "Governor, Deputy Governors ... at 31 December 2025"). `since` left null for Jónsson, Brynjólfsson and Sigurgísladóttir because their appointment dates appear only in search snippets (Brynjólfsson from 2024-08-01; Sigurgísladóttir 2023; Jónsson 2019-08). |
| Carolyn A. Wilkins — FPC term dates | Listed on the FPC page; BoE biography URL could not be located (404 for two guesses). | Included in the JSON with `since: null`; only the FPC page is cited. |
| Jonathan Haskel — OBR Chair start date | obr.uk and gov.uk news: nominated 2026-06-23, confirmed by Treasury Committee 2026-07-16, "takes up post later this year". | Included in JSON with `since: null`; listed as "Chair" on obr.uk/who-we-are. |
| Catherine L Mann — first-term start | Bio shows the current (second) term 2024-09-01 to 2027-08-31 only. | Included with `since: "2021-09"` (inferred from the 3-year first term) — flagged in the note; change to `"2024-09"` or null if inference is unwanted. |
| David Postings — UK Finance CEO start month | Page says "appointed CEO in 2021". | Included with `since: null`. Also: **no `group` value fits an industry body**; `intl_org` was used as a placeholder — please pick (or extend the README list). |
| Signe Krogstrup / Marja Nykänen start month | Bios say "since 2020" / "Deputy Governor since 2018" without a month. | Included with `since: null`. |
| Martina Lawless — ESRI Director start date | ESRI governance page names her Director; start 2025-06-01 appears only in a search snippet of the ESRI Financial Statements 2024. | Included with `since: null`. |
| Irish Minister for Finance page on gov.ie | gov.ie returned 403 to WebFetch, but **curl with browser headers succeeded** on the biography page. | Simon Harris **is** included (verified: appointed Minister for Finance 2025-11-18). |

## 4. Verification sources used (one page per institution, plus bios where cited)

- BoE MPC: https://www.bankofengland.co.uk/about/people/monetary-policy-committee ; FPC: https://www.bankofengland.co.uk/about/people/financial-policy-committee ; individual bios as cited in each entry.
- FCA Board: https://www.fca.org.uk/about/who-we-are/fca-board
- HM Treasury: https://www.gov.uk/government/organisations/hm-treasury ; https://www.gov.uk/government/ministers/chancellor-of-the-exchequer ; https://www.gov.uk/government/people/lucy-rigby
- OBR: https://obr.uk/about-the-obr/who-we-are/
- UK Finance: https://www.ukfinance.org.uk/about-us/our-people
- Central Bank of Ireland: https://www.centralbank.ie/about/who-we-are/our-senior-team-bios (+ /bios for dates)
- Department of Finance (IE): https://www.gov.ie/en/department-of-finance/biographies/simon-harris/
- Riksbank: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/ (+ member bios)
- Norges Bank: https://www.norges-bank.no/en/topics/about/Organisation/The-Executive-Board/
- Danmarks Nationalbank: https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments (+ bios)
- Bank of Finland: https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/ (+ bios)
- Central Bank of Iceland: Annual Report 2025 PDF, https://cb.is/library/?itemid=567a61a0-055f-4b80-ade5-632ad87f3238
- NIESR: https://niesr.ac.uk/people/david-aikman ; Resolution Foundation: https://www.resolutionfoundation.org/about-us/team/ruth-curtice/ ; ESRI: https://www.esri.ie/about-us/esri-governance

## 5. Notes on conventions used in the JSON

- `org` tokens follow the crawler's organizer_short list (`BoE`→ existing entries keep `"Bank of England"` as `org` with `"BoE"` alias, so new BoE entries do the same for consistency; `FCA`, `HM Treasury`, `OBR`, `UK Finance`, `Central Bank of Ireland`, `Riksbank`, `Norges Bank`, `Danmarks Nationalbank`, `Bank of Finland`, `Sedlabanki`, `NIESR`, `Resolution Foundation`, `ESRI`). Irish ministry uses `"Department of Finance (Ireland)"` with `"Department of Finance"` / `"An Roinn Airgeadais"` aliases — adjust if the crawler uses another token.
- Local-language names are in `org_aliases` (Sveriges Riksbank, Seðlabanki Íslands, Suomen Pankki / Finlands Bank, Banc Ceannais na hÉireann, Nationalbanken).
- `require_org: true` set for common names (Alan Taylor, Stephen Blyth, Jonathan Hall, Liz Oakes, Sarah Pritchard, John Healey, Simon Harris, Per Jansson, David Postings, David Aikman).
- External MPC/FPC members are `group: ncb`, tier 2, `org: "Bank of England"`, with their university added to `org_aliases` where the bio states it (Dhingra → LSE, Taylor → Columbia).


## 提案エントリ(JSON。承認後そのまま追記する)

```json
[
 {
  "id": "swati-dhingra",
  "name": "Swati Dhingra",
  "aliases": [
   "Dr Swati Dhingra"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "London School of Economics",
   "LSE"
  ],
  "position": "External member, Monetary Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2022-08",
  "require_org": false,
  "source": "https://www.bankofengland.co.uk/about/people/swati-dhingra/biography",
  "checked": "2026-10-19",
  "note": "MPC page lists her as 'Dr Swati Dhingra'. First term 2022-08-09; reappointed Feb 2025, second term 2025-08-09 to 2028-08-08. Associate Professor of Economics, LSE (Centre for Economic Performance)."
 },
 {
  "id": "megan-greene",
  "name": "Megan Greene",
  "aliases": [],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Monetary Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2023-07",
  "require_org": false,
  "source": "https://www.bankofengland.co.uk/about/people/megan-greene/biography",
  "checked": "2026-10-19",
  "note": "Term 2023-07-05; reappointed, second term runs to 2029-07-04."
 },
 {
  "id": "catherine-l-mann",
  "name": "Catherine L Mann",
  "aliases": [
   "Catherine Mann",
   "Catherine L. Mann"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Monetary Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2021-09",
  "require_org": false,
  "source": "https://www.bankofengland.co.uk/about/people/catherine-mann/biography",
  "checked": "2026-10-19",
  "note": "Bio shows current (second) term 2024-09-01 to 2027-08-31, reappointed 2024-03-18. 'since' 2021-09 is inferred from the 3-year first term; the bio does not state the first-term start explicitly."
 },
 {
  "id": "alan-taylor",
  "name": "Alan Taylor",
  "aliases": [
   "Professor Alan Taylor",
   "Alan M. Taylor"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Columbia University"
  ],
  "position": "External member, Monetary Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2024-09",
  "require_org": true,
  "source": "https://www.bankofengland.co.uk/about/people/alan-taylor/biography",
  "checked": "2026-10-19",
  "note": "Term 2024-09-02 to 2027-09-01. Professor of International and Public Affairs, Columbia University. MPC page lists him as 'Professor Alan Taylor'."
 },
 {
  "id": "stephen-blyth",
  "name": "Stephen Blyth",
  "aliases": [],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Financial Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2025-11",
  "require_org": true,
  "source": "https://www.bankofengland.co.uk/about/people/stephen-blyth/biography",
  "checked": "2026-10-19",
  "note": "Term 2025-11-01 to 2028-10-31."
 },
 {
  "id": "jonathan-hall",
  "name": "Jonathan Hall",
  "aliases": [],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Financial Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2020-09",
  "require_org": true,
  "source": "https://www.bankofengland.co.uk/about/people/jonathan-hall/biography",
  "checked": "2026-10-19",
  "note": "Term 2020-09-01 to 2026-12-31 (expires soon; re-check in 2027-01)."
 },
 {
  "id": "randall-kroszner",
  "name": "Randall Kroszner",
  "aliases": [
   "Randall S. Kroszner",
   "Randy Kroszner"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Financial Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2023-02",
  "require_org": false,
  "source": "https://www.bankofengland.co.uk/about/people/randall-kroszner/biography",
  "checked": "2026-10-19",
  "note": "FPC term 2023-02-01 to 2029-12-31; also external member of the FMIC (2024-01-01 to 2029-12-31). Professor at University of Chicago Booth; former Fed Governor."
 },
 {
  "id": "liz-oakes",
  "name": "Liz Oakes",
  "aliases": [
   "Elizabeth Oakes"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Financial Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": "2024-06",
  "require_org": true,
  "source": "https://www.bankofengland.co.uk/about/people/liz-oakes/biography",
  "checked": "2026-10-19",
  "note": "Term 2024-06-03 to 2027-06-02."
 },
 {
  "id": "carolyn-wilkins",
  "name": "Carolyn A. Wilkins",
  "aliases": [
   "Carolyn Wilkins"
  ],
  "org": "Bank of England",
  "org_aliases": [
   "BoE",
   "Bank of England"
  ],
  "position": "External member, Financial Policy Committee",
  "group": "ncb",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://www.bankofengland.co.uk/about/people/financial-policy-committee",
  "checked": "2026-10-19",
  "note": "Listed on the FPC page as 'Carolyn A. Wilkins, External member, Financial Policy Committee'. Individual biography URL not found (404), so term dates unverified. Former Senior Deputy Governor, Bank of Canada."
 },
 {
  "id": "nikhil-rathi",
  "name": "Nikhil Rathi",
  "aliases": [],
  "org": "FCA",
  "org_aliases": [
   "Financial Conduct Authority"
  ],
  "position": "Chief Executive",
  "group": "supervisor",
  "tier": 1,
  "since": "2020-10",
  "require_org": false,
  "source": "https://www.fca.org.uk/about/who-we-are/fca-board",
  "checked": "2026-10-19",
  "note": "CEO from 2020-10-01 (FCA Board page). Also sits on the BoE FPC as 'Executive FCA Board member, Chief Executive, FCA'."
 },
 {
  "id": "ashley-alder",
  "name": "Ashley Alder",
  "aliases": [],
  "org": "FCA",
  "org_aliases": [
   "Financial Conduct Authority"
  ],
  "position": "Chair",
  "group": "supervisor",
  "tier": 1,
  "since": "2023-02",
  "require_org": false,
  "source": "https://www.fca.org.uk/about/who-we-are/fca-board",
  "checked": "2026-10-19",
  "note": "Chair of the FCA Board from February 2023."
 },
 {
  "id": "sarah-pritchard",
  "name": "Sarah Pritchard",
  "aliases": [],
  "org": "FCA",
  "org_aliases": [
   "Financial Conduct Authority"
  ],
  "position": "Deputy Chief Executive",
  "group": "supervisor",
  "tier": 2,
  "since": "2025-06",
  "require_org": true,
  "source": "https://www.fca.org.uk/about/who-we-are/fca-board",
  "checked": "2026-10-19",
  "note": "Deputy CEO and executive Board member from June 2025."
 },
 {
  "id": "john-healey",
  "name": "John Healey",
  "aliases": [
   "Rt Hon John Healey MP",
   "John Healey MP"
  ],
  "org": "HM Treasury",
  "org_aliases": [
   "HM Treasury",
   "Her Majesty's Treasury",
   "His Majesty's Treasury",
   "HMT",
   "UK Treasury",
   "The Treasury"
  ],
  "position": "Chancellor of the Exchequer",
  "group": "government",
  "tier": 1,
  "since": "2026-07",
  "require_org": true,
  "source": "https://www.gov.uk/government/ministers/chancellor-of-the-exchequer",
  "checked": "2026-10-19",
  "note": "Appointed 2026-07-20 (gov.uk ministers page). HM Treasury organisation page lists 'The Rt Hon John Healey MP, Chancellor of the Exchequer'."
 },
 {
  "id": "lucy-rigby",
  "name": "Lucy Rigby",
  "aliases": [
   "Lucy Rigby KC MP",
   "Lucy Rigby KC"
  ],
  "org": "HM Treasury",
  "org_aliases": [
   "HM Treasury",
   "Her Majesty's Treasury",
   "His Majesty's Treasury",
   "HMT",
   "UK Treasury",
   "The Treasury"
  ],
  "position": "Economic Secretary to the Treasury (City Minister)",
  "group": "government",
  "tier": 2,
  "since": "2026-07",
  "require_org": false,
  "source": "https://www.gov.uk/government/people/lucy-rigby",
  "checked": "2026-10-19",
  "note": "Appointed Minister of State (Economic Secretary to the Treasury) 2026-07-21. gov.uk describes the post as 'the City Minister responsible for financial services'."
 },
 {
  "id": "jonathan-haskel",
  "name": "Jonathan Haskel",
  "aliases": [
   "Professor Jonathan Haskel",
   "Jonathan Haskel CBE"
  ],
  "org": "OBR",
  "org_aliases": [
   "Office for Budget Responsibility",
   "Imperial College Business School",
   "Imperial College London"
  ],
  "position": "Chair, Budget Responsibility Committee",
  "group": "government",
  "tier": 1,
  "since": null,
  "require_org": false,
  "source": "https://obr.uk/about-the-obr/who-we-are/",
  "checked": "2026-10-19",
  "note": "Listed as 'Chair' on obr.uk/who-we-are. Nominated by the Chancellor 2026-06-23, confirmed by the Treasury Committee 2026-07-16 (https://obr.uk/professor-jonathan-haskel-confirmed-as-next-chair-of-the-obr/); exact start date not stated on the pages fetched. Professor of Economics, Imperial College; former external MPC member (2018-2024)."
 },
 {
  "id": "david-postings",
  "name": "David Postings",
  "aliases": [],
  "org": "UK Finance",
  "org_aliases": [
   "UK Finance Ltd"
  ],
  "position": "Chief Executive",
  "group": "intl_org",
  "tier": 2,
  "since": null,
  "require_org": true,
  "source": "https://www.ukfinance.org.uk/about-us/our-people",
  "checked": "2026-10-19",
  "note": "Appointed CEO in 2021 (month not shown on page; NED since 2018). group: no exact fit for an industry body; 'intl_org' used as placeholder - user to decide."
 },
 {
  "id": "vasileios-madouros",
  "name": "Vasileios Madouros",
  "aliases": [],
  "org": "Central Bank of Ireland",
  "org_aliases": [
   "Banc Ceannais na hÉireann",
   "Central Bank of Ireland"
  ],
  "position": "Deputy Governor, Monetary and Financial Stability",
  "group": "ncb",
  "tier": 2,
  "since": "2022-11",
  "require_org": false,
  "source": "https://www.centralbank.ie/about/who-we-are/our-senior-team-bios/bios",
  "checked": "2026-10-19",
  "note": "Appointed November 2022 (senior team bios page)."
 },
 {
  "id": "mary-elizabeth-mcmunn",
  "name": "Mary-Elizabeth McMunn",
  "aliases": [
   "Mary Elizabeth McMunn"
  ],
  "org": "Central Bank of Ireland",
  "org_aliases": [
   "Banc Ceannais na hÉireann",
   "Central Bank of Ireland"
  ],
  "position": "Deputy Governor, Financial Regulation",
  "group": "ncb",
  "tier": 2,
  "since": "2025-01",
  "require_org": false,
  "source": "https://www.centralbank.ie/about/who-we-are/our-senior-team-bios/bios",
  "checked": "2026-10-19",
  "note": "Appointed 2025-01-01."
 },
 {
  "id": "colm-kincaid",
  "name": "Colm Kincaid",
  "aliases": [],
  "org": "Central Bank of Ireland",
  "org_aliases": [
   "Banc Ceannais na hÉireann",
   "Central Bank of Ireland"
  ],
  "position": "Deputy Governor, Consumer and Investor Protection",
  "group": "ncb",
  "tier": 2,
  "since": "2025-08",
  "require_org": false,
  "source": "https://www.centralbank.ie/about/who-we-are/our-senior-team-bios/bios",
  "checked": "2026-10-19",
  "note": "Appointed 2025-08-01."
 },
 {
  "id": "simon-harris",
  "name": "Simon Harris",
  "aliases": [
   "Simon Harris TD"
  ],
  "org": "Department of Finance (Ireland)",
  "org_aliases": [
   "Department of Finance",
   "An Roinn Airgeadais",
   "Government of Ireland",
   "Irish Government"
  ],
  "position": "Tánaiste and Minister for Finance",
  "group": "government",
  "tier": 1,
  "since": "2025-11",
  "require_org": true,
  "source": "https://www.gov.ie/en/department-of-finance/biographies/simon-harris/",
  "checked": "2026-10-19",
  "note": "Appointed Minister for Finance 2025-11-18; Tánaiste since 2025-01-23 (gov.ie biography, last updated 2026-07-06). Former Taoiseach (2024-04 to 2025-01)."
 },
 {
  "id": "erik-thedeen",
  "name": "Erik Thedéen",
  "aliases": [
   "Erik Thedeen"
  ],
  "org": "Riksbank",
  "org_aliases": [
   "Sveriges Riksbank",
   "Sveriges riksbank",
   "Swedish central bank"
  ],
  "position": "Governor",
  "group": "ncb",
  "tier": 1,
  "since": "2023-01",
  "require_org": false,
  "source": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/",
  "checked": "2026-10-19",
  "note": "Governor and Chairman of the Executive Board from 2023-01-01, six-year term (bio: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/erik-thedeen/)."
 },
 {
  "id": "aino-bunge",
  "name": "Aino Bunge",
  "aliases": [],
  "org": "Riksbank",
  "org_aliases": [
   "Sveriges Riksbank",
   "Sveriges riksbank",
   "Swedish central bank"
  ],
  "position": "First Deputy Governor",
  "group": "ncb",
  "tier": 2,
  "since": "2022-12",
  "require_org": false,
  "source": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/",
  "checked": "2026-10-19",
  "note": "Deputy Governor from 2022-12-01; First Deputy Governor from 2025-10-11, term to 2028-12-01 (bio: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/aino-bunge/)."
 },
 {
  "id": "per-jansson",
  "name": "Per Jansson",
  "aliases": [],
  "org": "Riksbank",
  "org_aliases": [
   "Sveriges Riksbank",
   "Sveriges riksbank",
   "Swedish central bank"
  ],
  "position": "Deputy Governor",
  "group": "ncb",
  "tier": 2,
  "since": "2012-01",
  "require_org": true,
  "source": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/",
  "checked": "2026-10-19",
  "note": "Deputy Governor since 2012-01-01; current mandate to 2027-12-31 (bio: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/per-jansson/)."
 },
 {
  "id": "anna-seim",
  "name": "Anna Seim",
  "aliases": [],
  "org": "Riksbank",
  "org_aliases": [
   "Sveriges Riksbank",
   "Sveriges riksbank",
   "Swedish central bank"
  ],
  "position": "Deputy Governor",
  "group": "ncb",
  "tier": 2,
  "since": "2024-05",
  "require_org": false,
  "source": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/",
  "checked": "2026-10-19",
  "note": "Took up post 2024-05-22, six-year term (bio: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/anna-seim/)."
 },
 {
  "id": "goran-hjelm",
  "name": "Göran Hjelm",
  "aliases": [
   "Goran Hjelm"
  ],
  "org": "Riksbank",
  "org_aliases": [
   "Sveriges Riksbank",
   "Sveriges riksbank",
   "Swedish central bank"
  ],
  "position": "Deputy Governor",
  "group": "ncb",
  "tier": 2,
  "since": "2026-03",
  "require_org": false,
  "source": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/",
  "checked": "2026-10-19",
  "note": "Took up post 2026-03-02, six-year term; succeeded Anna Breman (bio: https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/goran-hjelm/)."
 },
 {
  "id": "ida-wolden-bache",
  "name": "Ida Wolden Bache",
  "aliases": [],
  "org": "Norges Bank",
  "org_aliases": [
   "Norges Bank",
   "Norway's central bank",
   "Central Bank of Norway"
  ],
  "position": "Governor",
  "group": "ncb",
  "tier": 1,
  "since": "2022-04",
  "require_org": false,
  "source": "https://www.norges-bank.no/en/topics/about/Organisation/The-Executive-Board/",
  "checked": "2026-10-19",
  "note": "Governor and Chair of the Executive Board from 2022-04-08; term to 2028."
 },
 {
  "id": "pal-longva",
  "name": "Pål Longva",
  "aliases": [
   "Pal Longva"
  ],
  "org": "Norges Bank",
  "org_aliases": [
   "Norges Bank",
   "Norway's central bank",
   "Central Bank of Norway"
  ],
  "position": "Deputy Governor (First Deputy Chair of the Executive Board)",
  "group": "ncb",
  "tier": 2,
  "since": "2022-08",
  "require_org": false,
  "source": "https://www.norges-bank.no/en/topics/about/Organisation/The-Executive-Board/",
  "checked": "2026-10-19",
  "note": "Appointed 2022-08-29, term to 2028; particular responsibility for central banking operations."
 },
 {
  "id": "oystein-borsum",
  "name": "Øystein Børsum",
  "aliases": [
   "Oystein Borsum",
   "Øystein Borsum"
  ],
  "org": "Norges Bank",
  "org_aliases": [
   "Norges Bank",
   "Norway's central bank",
   "Central Bank of Norway"
  ],
  "position": "Deputy Governor (Second Deputy Chair of the Executive Board)",
  "group": "ncb",
  "tier": 2,
  "since": "2021-08",
  "require_org": false,
  "source": "https://www.norges-bank.no/en/topics/about/Organisation/The-Executive-Board/",
  "checked": "2026-10-19",
  "note": "Appointed 2021-08-02, term to 2027; particular responsibility for the Government Pension Fund Global."
 },
 {
  "id": "christian-kettel-thomsen",
  "name": "Christian Kettel Thomsen",
  "aliases": [
   "Christian Thomsen"
  ],
  "org": "Danmarks Nationalbank",
  "org_aliases": [
   "Danmarks Nationalbank",
   "Nationalbanken",
   "Danish central bank",
   "National Bank of Denmark"
  ],
  "position": "Governor (by Royal Appointment) and Chairman of the Board of Governors",
  "group": "ncb",
  "tier": 1,
  "since": "2023-02",
  "require_org": false,
  "source": "https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments",
  "checked": "2026-10-19",
  "note": "Chairman since 2023-02-01 (bio: https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments/christian-kettel-thomsen)."
 },
 {
  "id": "signe-krogstrup",
  "name": "Signe Krogstrup",
  "aliases": [],
  "org": "Danmarks Nationalbank",
  "org_aliases": [
   "Danmarks Nationalbank",
   "Nationalbanken",
   "Danish central bank",
   "National Bank of Denmark"
  ],
  "position": "Governor",
  "group": "ncb",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments",
  "checked": "2026-10-19",
  "note": "Governor since 2020 (month not shown; bio: https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments/signe-krogstrup)."
 },
 {
  "id": "ulrik-nodgaard",
  "name": "Ulrik Nødgaard",
  "aliases": [
   "Ulrik Nodgaard",
   "Ulrik Noedgaard"
  ],
  "org": "Danmarks Nationalbank",
  "org_aliases": [
   "Danmarks Nationalbank",
   "Nationalbanken",
   "Danish central bank",
   "National Bank of Denmark"
  ],
  "position": "Governor",
  "group": "ncb",
  "tier": 2,
  "since": "2024-08",
  "require_org": false,
  "source": "https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments",
  "checked": "2026-10-19",
  "note": "Governor since 2024-08-15 (bio: https://www.nationalbanken.dk/en/about-us/board-of-governors-group-management-and-departments/ulrik-noedgaard)."
 },
 {
  "id": "marja-nykanen",
  "name": "Marja Nykänen",
  "aliases": [
   "Marja Nykanen"
  ],
  "org": "Bank of Finland",
  "org_aliases": [
   "Suomen Pankki",
   "Finlands Bank",
   "Suomen Pankki - Finlands Bank",
   "Bank of Finland"
  ],
  "position": "Deputy Governor",
  "group": "ncb",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/",
  "checked": "2026-10-19",
  "note": "Member of the Board since 2017-02-01; Deputy Governor since 2018 (month not shown; bio: https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/marja-nykanen/)."
 },
 {
  "id": "tuomas-valimaki",
  "name": "Tuomas Välimäki",
  "aliases": [
   "Tuomas Valimaki"
  ],
  "org": "Bank of Finland",
  "org_aliases": [
   "Suomen Pankki",
   "Finlands Bank",
   "Suomen Pankki - Finlands Bank",
   "Bank of Finland"
  ],
  "position": "Member of the Board",
  "group": "ncb",
  "tier": 2,
  "since": "2018-07",
  "require_org": false,
  "source": "https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/",
  "checked": "2026-10-19",
  "note": "Board member since 2018-07-12; alternate member of the ECB Governing Council (bio: https://www.suomenpankki.fi/en/bank-of-finland/organisation/board/tuomas-valimaki/)."
 },
 {
  "id": "asgeir-jonsson",
  "name": "Ásgeir Jónsson",
  "aliases": [
   "Asgeir Jonsson"
  ],
  "org": "Sedlabanki",
  "org_aliases": [
   "Seðlabanki Íslands",
   "Sedlabanki Islands",
   "Central Bank of Iceland",
   "Seðlabankinn"
  ],
  "position": "Governor",
  "group": "ncb",
  "tier": 1,
  "since": null,
  "require_org": false,
  "source": "https://cb.is/library/?itemid=567a61a0-055f-4b80-ade5-632ad87f3238",
  "checked": "2026-10-19",
  "note": "Listed as Governor as of 2025-12-31 in the Central Bank of Iceland Annual Report 2025 (cb.is). Start date (2019) not on the page fetched; cb.is governance HTML page returned empty content."
 },
 {
  "id": "thorarinn-g-petursson",
  "name": "Thórarinn G. Pétursson",
  "aliases": [
   "Þórarinn G. Pétursson",
   "Thorarinn G. Petursson",
   "Thórarinn Pétursson"
  ],
  "org": "Sedlabanki",
  "org_aliases": [
   "Seðlabanki Íslands",
   "Sedlabanki Islands",
   "Central Bank of Iceland",
   "Seðlabankinn"
  ],
  "position": "Deputy Governor for Monetary Policy",
  "group": "ncb",
  "tier": 2,
  "since": "2025-01",
  "require_org": false,
  "source": "https://cb.is/library/?itemid=567a61a0-055f-4b80-ade5-632ad87f3238",
  "checked": "2026-10-19",
  "note": "Annual Report 2025: Deputy Governor for Monetary Policy 'following his appointment at the beginning of the year' (2025). Former Chief Economist."
 },
 {
  "id": "tomas-brynjolfsson",
  "name": "Tómas Brynjólfsson",
  "aliases": [
   "Tomas Brynjolfsson"
  ],
  "org": "Sedlabanki",
  "org_aliases": [
   "Seðlabanki Íslands",
   "Sedlabanki Islands",
   "Central Bank of Iceland",
   "Seðlabankinn"
  ],
  "position": "Deputy Governor for Financial Stability",
  "group": "ncb",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://cb.is/library/?itemid=567a61a0-055f-4b80-ade5-632ad87f3238",
  "checked": "2026-10-19",
  "note": "Annual Report 2025. Appointment from 2024-08-01 reported in a cb.is news item that could not be fetched (empty content), so 'since' left null."
 },
 {
  "id": "bjork-sigurgisladottir",
  "name": "Björk Sigurgísladóttir",
  "aliases": [
   "Bjork Sigurgisladottir"
  ],
  "org": "Sedlabanki",
  "org_aliases": [
   "Seðlabanki Íslands",
   "Sedlabanki Islands",
   "Central Bank of Iceland",
   "Seðlabankinn"
  ],
  "position": "Deputy Governor for Financial Supervision",
  "group": "ncb",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://cb.is/library/?itemid=567a61a0-055f-4b80-ade5-632ad87f3238",
  "checked": "2026-10-19",
  "note": "Annual Report 2025. Appointed 2023 per search snippets; not verified on a fetched page."
 },
 {
  "id": "david-aikman",
  "name": "David Aikman",
  "aliases": [
   "Professor David Aikman",
   "Dr David Aikman"
  ],
  "org": "NIESR",
  "org_aliases": [
   "National Institute of Economic and Social Research"
  ],
  "position": "Director",
  "group": "academia",
  "tier": 2,
  "since": "2025-07",
  "require_org": true,
  "source": "https://niesr.ac.uk/people/david-aikman",
  "checked": "2026-10-19",
  "note": "Joined NIESR as Director July 2025 (previously King's College London; 17 years at the BoE)."
 },
 {
  "id": "ruth-curtice",
  "name": "Ruth Curtice",
  "aliases": [],
  "org": "Resolution Foundation",
  "org_aliases": [
   "The Resolution Foundation"
  ],
  "position": "Chief Executive",
  "group": "academia",
  "tier": 2,
  "since": "2025-01",
  "require_org": false,
  "source": "https://www.resolutionfoundation.org/about-us/team/ruth-curtice/",
  "checked": "2026-10-19",
  "note": "Chief Executive since January 2025 (formerly Director of fiscal policy, HM Treasury)."
 },
 {
  "id": "martina-lawless",
  "name": "Martina Lawless",
  "aliases": [
   "Prof. Martina Lawless",
   "Professor Martina Lawless"
  ],
  "org": "ESRI",
  "org_aliases": [
   "Economic and Social Research Institute",
   "The Economic and Social Research Institute"
  ],
  "position": "Director",
  "group": "academia",
  "tier": 2,
  "since": null,
  "require_org": false,
  "source": "https://www.esri.ie/about-us/esri-governance",
  "checked": "2026-10-19",
  "note": "Named as Director on the ESRI governance page. Took up post 2025-06-01 per ESRI Financial Statements 2024 (search snippet; not verified on a fetched page)."
 }
]
```
