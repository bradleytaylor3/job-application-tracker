# Job Application Tracker

A small Python tool that logs into your Workday candidate portals, pulls the
status of every application you've submitted, and generates a single
dark-themed HTML report (plus a CSV) so you can see everything at a glance
instead of checking each company's site by hand.

Applications outside Workday can be tracked too, via a simple manual entry
list that gets merged into the same report.

## How it works

- [Playwright](https://playwright.dev/python/) drives a real (headless by
  default) Chromium browser: it logs into each configured Workday site,
  navigates to the candidate's "My Applications" section, and scrapes the
  job title, status, and date applied for every row.
- Results from every site are combined into one report, grouped by company.
- Non-Workday applications you're tracking by hand can be added to
  `manual_applications.json` and they'll show up in the same report.

## Setup

```
pip install -r requirements.txt
playwright install chromium
```

1. Copy `.env.example` → `.env` and fill in real email/password credentials
   for each site.
2. Copy `sites_config.example.json` → `sites_config.json` and list your
   actual sites (see [Configuring sites](#configuring-sites) below).
3. Run:

```
python tracker.py
```

This runs headless, checks every configured site, writes a timestamped
CSV + HTML report to `reports/`, and opens the HTML report in your browser
automatically.

## Configuring sites

Each entry in `sites_config.json` is one Workday tenant:

```json
{
  "name": "Some Company",
  "login_url": "https://company.wd5.myworkdayjobs.com/en-US/CareerSite/login",
  "applications_url": "https://company.wd5.myworkdayjobs.com/en-US/CareerSite/userHome",
  "email_env": "SOME_COMPANY_EMAIL",
  "password_env": "SOME_COMPANY_PASSWORD"
}
```

- `login_url` — the site's Workday sign-in page.
- `applications_url` — where "My Applications" lives after login. If you
  don't know it, omit this field and the script will click the
  applications link on the page instead.
- `email_env` / `password_env` — the variable names in `.env` that hold
  this site's credentials. Every site needs its own pair, even if the
  email is the same across sites.

**Multiple logins for the same company** (e.g. two personal accounts) just
need two separate entries pointing at the same `login_url`/
`applications_url`, each with its own `email_env`/`password_env` — see the
two-entry example in `sites_config.example.json`.

Workday's login form and applications table use the same underlying
`data-automation-id` attributes across most tenants (see
`DEFAULT_SELECTORS` in `tracker.py`), so most sites work with no further
configuration. If a specific company's site is customized enough to break
this, add a `"selectors"` object to that site's entry to override just the
selectors that differ — see [Troubleshooting a site](#troubleshooting-a-site).

## Tracking applications outside Workday (manual entries)

For sites that aren't Workday, or that you don't want to script a login
for, add them to `manual_applications.json` instead:

```json
[
  { "company": "Some Company", "role": "Software Engineer", "date_applied": "2026-07-01", "status": "Waiting" },
  { "company": "Another Company", "date_applied": "2026-06-15" }
]
```

- `company` and `date_applied` are required.
- `role` is optional — fills the Job Title column if given, otherwise
  shows as `—`.
- `status` is optional and defaults to `"Waiting"`.

These entries are merged into the same CSV/HTML report as their own
section per company, right alongside the scraped Workday sites — see
`manual_applications.example.json` for reference. Applying to multiple
roles at the same company is fine; just add one entry per role and
they'll appear as separate rows under that company's section.

Editing this JSON by hand works fine, but if you'd rather be walked
through it conversationally (and have something check whether you're
about to log a duplicate), see `add-application-prompt.md` — a prompt you
can paste into any AI chat along with your current
`manual_applications.json` contents.

## Troubleshooting a site

Run with a visible browser so you can see what's happening, and it'll
pause on any error instead of closing immediately:

```
python tracker.py --show
```

On a timeout, a screenshot is also saved to `reports/debug_<Site Name>.png`
showing exactly what the page looked like when it gave up — useful if
you're not running with `--show` or the pause already closed.

Common issues and what tends to fix them:

- **Click intercepted by a cookie banner** — already handled by
  `dismiss_cookie_banner()`, but if a site uses different button text than
  `"Decline"`/`"Reject All"`/`"Accept Cookies"`/`"Accept All"`, add it to
  `COOKIE_BANNER_BUTTON_TEXTS` in `tracker.py`.
- **Sign-in click times out even though the selector "resolves"** — some
  Workday themes render the real submit button as `aria-hidden` with a
  separate clickable overlay on top. The script already clicks by
  accessible role/name (`"Sign In"`) to route around this; if a site uses
  different button text, override `sign_in_button_text` for that site.
- **Login form appears to submit but just reloads a blank login page** —
  this happens when fields get filled faster than the page's JS can
  register them. The script already paces every step with ~1 second
  pauses; if a particularly slow site still races, increase the relevant
  `page.wait_for_timeout(...)` calls in `check_site()`.
- **Applications table selector times out but login succeeded** — check
  the debug screenshot to confirm you actually reached the applications
  page, then inspect the real `data-automation-id` attributes for that
  site's table (e.g. via browser dev tools) and add a `"selectors"`
  override in `sites_config.json`.

## Repo hygiene

- `.env`, `sites_config.json`, `manual_applications.json`, and `reports/`
  are all gitignored — they hold real credentials, real login URLs, and
  personal application data. Only the `*.example.json` templates,
  `tracker.py`, and this README are meant to be committed.
- Each run writes a new timestamped file to `reports/` rather than
  overwriting the last one, so you keep a history of past statuses.

## Requirements

- Python 3.9+
- See `requirements.txt` (`playwright`, `python-dotenv`)
