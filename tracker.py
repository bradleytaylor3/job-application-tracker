"""
Checks job application status across multiple Workday candidate portals.

Setup:
1. pip install -r requirements.txt
2. playwright install chromium
3. Copy .env.example to .env and fill in credentials for each site
4. Copy sites_config.example.json to sites_config.json and fill in your sites
5. Run: python tracker.py           (headless, opens an HTML report when done)
   or:  python tracker.py --show    (visible browser, pauses on errors so
                                      you can inspect the page and fix selectors)
"""

import csv
import json
import os
import sys
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

CONFIG_PATH = Path(__file__).parent / "sites_config.json"
MANUAL_PATH = Path(__file__).parent / "manual_applications.json"
REPORTS_DIR = Path(__file__).parent / "reports"

# Workday candidate portals share this structure across most tenants.
# If a specific company's site uses different markup, add a "selectors"
# object to that site's entry in sites_config.json to override any of these.
DEFAULT_SELECTORS = {
    "email_input": 'input[data-automation-id="email"]',
    "password_input": 'input[data-automation-id="password"]',
    # Workday renders the real signInSubmitButton as aria-hidden and overlays
    # a role="button" div that actually handles the click, so we target it by
    # accessible name instead of the (non-interactive) CSS id.
    "sign_in_button_text": "Sign In",
    "applications_link": 'a[data-automation-id="myApplications"]',
    # Verified against a live Cengage tenant - these are Workday's own
    # platform-wide component names (candidate-home-app), not something
    # Cengage customized, so they should hold across tenants.
    "application_row": 'section[data-automation-id="applicationsSectionHeading"] tr[data-automation-id="taskListRow"]',
    "job_title": '[data-automation-id="applicationTitle"]',
    "status": '[data-automation-id="applicationStatus"]',
    "date_applied": 'td:nth-child(4)',
}


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Missing {CONFIG_PATH}.\n"
            "Copy sites_config.example.json to sites_config.json and fill in your sites."
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_manual_entries():
    if not MANUAL_PATH.exists():
        return []
    entries = json.loads(MANUAL_PATH.read_text(encoding="utf-8"))
    return [
        {
            "site": entry["company"],
            "job_title": entry.get("role") or "",
            "status": entry.get("status") or "Waiting",
            "date_applied": entry.get("date_applied", ""),
            "error": False,
        }
        for entry in entries
    ]


# Cookie-consent banners appear on a fresh browser profile every run (unlike
# a regular browser where you dismiss them once). Best-effort dismiss so they
# don't sit on top of the login button and block the click.
COOKIE_BANNER_BUTTON_TEXTS = ["Decline", "Reject All", "Accept Cookies", "Accept All"]


def dismiss_cookie_banner(page):
    for text in COOKIE_BANNER_BUTTON_TEXTS:
        try:
            page.click(f'button:has-text("{text}")', timeout=3000)
            return
        except PlaywrightTimeoutError:
            continue


def check_site(page, site, headless):
    selectors = {**DEFAULT_SELECTORS, **site.get("selectors", {})}
    email = os.environ.get(site["email_env"])
    password = os.environ.get(site["password_env"])
    if not email or not password:
        raise RuntimeError(
            f"Missing credentials for {site['name']} "
            f"(check .env for {site['email_env']} / {site['password_env']})"
        )

    results = []
    try:
        page.goto(site["login_url"], timeout=30000)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        dismiss_cookie_banner(page)
        page.wait_for_timeout(1000)

        page.fill(selectors["email_input"], email)
        page.wait_for_timeout(1000)

        page.fill(selectors["password_input"], password)
        page.wait_for_timeout(1000)

        page.get_by_role("button", name=selectors["sign_in_button_text"]).click(timeout=15000)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        if site.get("applications_url"):
            page.goto(site["applications_url"], timeout=30000)
        else:
            page.click(selectors["applications_link"])
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        page.wait_for_selector(selectors["application_row"], timeout=20000)
        rows = page.query_selector_all(selectors["application_row"])
        for row in rows:
            title_el = row.query_selector(selectors["job_title"])
            status_el = row.query_selector(selectors["status"])
            date_el = row.query_selector(selectors["date_applied"])
            results.append(
                {
                    "site": site["name"],
                    "job_title": title_el.inner_text().strip() if title_el else "",
                    "status": status_el.inner_text().strip() if status_el else "",
                    "date_applied": date_el.inner_text().strip() if date_el else "",
                    "error": False,
                }
            )
    except PlaywrightTimeoutError as e:
        debug_path = REPORTS_DIR / f"debug_{site['name']}.png"
        try:
            REPORTS_DIR.mkdir(exist_ok=True)
            page.screenshot(path=str(debug_path))
            print(f"  Saved debug screenshot to {debug_path}")
        except Exception:
            pass
        results.append(
            {
                "site": site["name"],
                "job_title": "",
                "status": f"Timed out / selector not found: {e}",
                "date_applied": "",
                "error": True,
            }
        )
        if not headless:
            try:
                input(f"[{site['name']}] Paused for inspection - press Enter to continue...")
            except (EOFError, OSError):
                pass
    return results


def main():
    headless = "--show" not in sys.argv
    sites = load_config()
    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        for site in sites:
            print(f"Checking {site['name']}...")
            context = browser.new_context()
            page = context.new_page()
            try:
                all_results.extend(check_site(page, site, headless))
            except Exception as e:
                print(f"  Failed: {e}")
                all_results.append(
                    {"site": site["name"], "job_title": "", "status": str(e), "date_applied": "", "error": True}
                )
            finally:
                context.close()
        browser.close()

    all_results.extend(load_manual_entries())

    save_csv(all_results)
    report_path = save_html(all_results)
    print(f"\nOpening report: {report_path}")
    webbrowser.open(report_path.as_uri())


def save_csv(results):
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"status_{ts}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["site", "job_title", "status", "date_applied", "error"])
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved CSV to {out_path}")
    return out_path


# Statuses containing any of these words get a colored badge in the HTML report.
STATUS_STYLES = {
    "reject": "background:#3a1f22; color:#f5a3ab;",
    "declin": "background:#3a1f22; color:#f5a3ab;",
    "no longer": "background:#3a1f22; color:#f5a3ab;",
    "not selected": "background:#3a1f22; color:#f5a3ab;",
    "offer": "background:#1f3a24; color:#8fe0a0;",
    "hire": "background:#1f3a24; color:#8fe0a0;",
    "interview": "background:#3a2f1f; color:#f0c987;",
    "review": "background:#1f2c3a; color:#8fbde0;",
    "progress": "background:#1f2c3a; color:#8fbde0;",
    "consideration": "background:#1f2c3a; color:#8fbde0;",
    "submitted": "background:#2a2a2a; color:#c9c9c9;",
    "receiv": "background:#2a2a2a; color:#c9c9c9;",
}


def badge_style(status: str) -> str:
    lower = status.lower()
    for keyword, style in STATUS_STYLES.items():
        if keyword in lower:
            return style
    return "background:#2a2a2a; color:#c9c9c9;"


def save_html(results):
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"status_{ts}.html"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    by_site = {}
    for r in results:
        by_site.setdefault(r["site"], []).append(r)

    sections = []
    for site, rows in sorted(by_site.items()):
        row_html = []
        for r in rows:
            if r.get("error"):
                row_html.append(
                    f'<tr><td colspan="3" class="error-cell">Could not fetch: {escape(r["status"])}</td></tr>'
                )
                continue
            style = badge_style(r["status"])
            row_html.append(
                "<tr>"
                f'<td>{escape(r["job_title"]) or "&mdash;"}</td>'
                f'<td><span class="badge" style="{style}">{escape(r["status"])}</span></td>'
                f'<td>{escape(r["date_applied"])}</td>'
                "</tr>"
            )
        sections.append(
            f"""
            <section>
              <h2>{escape(site)}</h2>
              <table>
                <thead><tr><th>Job Title</th><th>Status</th><th>Date Applied</th></tr></thead>
                <tbody>{''.join(row_html) or '<tr><td colspan="3">No applications found</td></tr>'}</tbody>
              </table>
            </section>
            """
        )

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Application Status Report</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    background: #121212; color: #e8e8e8;
    max-width: 860px; margin: 2rem auto; padding: 0 1rem;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0; }}
  .timestamp {{ color: #888; font-size: 0.85rem; margin-top: 0.25rem; margin-bottom: 2rem; }}
  section {{ margin-bottom: 2rem; }}
  h2 {{ font-size: 1.05rem; border-bottom: 1px solid #333; padding-bottom: 0.4rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.6rem; font-size: 0.9rem; }}
  thead th {{ color: #999; font-weight: 500; border-bottom: 1px solid #333; }}
  tbody tr:nth-child(odd) {{ background: #1a1a1a; }}
  .badge {{ padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.8rem; white-space: nowrap; }}
  .error-cell {{ color: #f5a3ab; font-style: italic; }}
</style>
</head>
<body>
  <h1>Application Status Report</h1>
  <div class="timestamp">Generated {escape(generated_at)}</div>
  {''.join(sections) if sections else '<p>No results.</p>'}
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved HTML report to {out_path}")
    return out_path


if __name__ == "__main__":
    main()
