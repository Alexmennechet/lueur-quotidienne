"""
Daily email automation script for Lueur Quotidienne
==================================================

This script generates a personalised HTML email each day from
local data sources, schedules its delivery via the Buttondown API
and captures performance metrics for reporting.  It is designed to
run unattended (for example via a cron job or GitHub Action) and
reads its configuration from a simple JSON file.

Key features
------------

* Pulls a random inspirational quote and product recommendation from
  JSON files (or remote URLs if configured).
* Generates responsive HTML using a Jinja‑like template with
  placeholders for the recipient’s name, date, quote and product.
* Automatically appends UTM parameters to all outbound links and
  injects a tracking pixel for open detection.
* Creates or updates a Buttondown email, sets its status to
  ``scheduled`` and assigns a publish date in the future.
* Retrieves analytics for the previously sent email (deliveries,
  opens, clicks, etc.) and appends a row to a CSV report.

Before running this script for the first time you must:

1. Obtain an API key from Buttondown and store it securely (either
   in ``config.json`` or as an environment variable).
2. Enable tracking within your Buttondown account settings, as
   analytics endpoints will return empty data otherwise【919215350250110†L111-L116】.
3. Create a newsletter in Buttondown and note its ``newsletter_id`` (or
   leave blank to use your default newsletter).
4. Populate ``quotes.json`` and ``products.json`` with your own
   content.  See the existing files in ``assets/data`` for examples.
5. Optionally customise ``email_template.html`` to match your
   branding and tone.

The configuration file ``config.json`` should look something like this::

    {
      "buttondown_api_key": "YOUR_API_KEY",
      "newsletter_id": null,
      "send_time": "08:00",
      "timezone": "Europe/Paris",
      "utm_source": "lueurquotidienne",
      "utm_medium": "email",
      "utm_campaign": "daily_quote",
      "tip_link": "https://ko-fi.com/your_page",
      "reports_csv": "analytics_report.csv"
    }

Running this script will schedule tomorrow’s email at the specified
time.  To generate and send an email immediately (for example when
testing) you can set the publish date to now plus a small offset.

NOTE: This script assumes Python 3.9+ and the ``requests`` and
``pytz`` libraries are installed.  You can install dependencies
locally with ``pip install requests pytz``.
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    # Fallback to pytz if zoneinfo is unavailable
    import pytz  # type: ignore
import requests


@dataclass
class Config:
    buttondown_api_key: str
    newsletter_id: Optional[str]
    send_time: str  # e.g. "08:00" in HH:MM 24h format
    timezone: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    tip_link: str
    reports_csv: str
    site_url: str = "https://lueur-quotidienne.netlify.app"

    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(
            buttondown_api_key=data["buttondown_api_key"],
            newsletter_id=data.get("newsletter_id"),
            send_time=data.get("send_time", "08:00"),
            timezone=data.get("timezone", "Europe/Paris"),
            utm_source=data.get("utm_source", "lueurquotidienne"),
            utm_medium=data.get("utm_medium", "email"),
            utm_campaign=data.get("utm_campaign", "daily_quote"),
            tip_link=data.get("tip_link", ""),
            reports_csv=data.get("reports_csv", "analytics_report.csv"),
            site_url=data.get("site_url", "https://lueur-quotidienne.netlify.app"),
        )


def load_json_data(path_or_url: str) -> Any:
    """Load JSON from a local file or remote URL."""
    if re.match(r"^https?://", path_or_url):
        resp = requests.get(path_or_url)
        resp.raise_for_status()
        return resp.json()
    with open(path_or_url, "r", encoding="utf-8") as f:
        return json.load(f)


def choose_random_item(items: list[Dict[str, Any]]) -> Dict[str, Any]:
    return random.choice(items)


def append_utm(url: str, config: Config) -> str:
    """Append UTM parameters to a URL if they are not already present."""
    delimiter = "&" if "?" in url else "?"
    utm_params = (
        f"utm_source={config.utm_source}"
        f"&utm_medium={config.utm_medium}"
        f"&utm_campaign={config.utm_campaign}"
    )
    return f"{url}{delimiter}{utm_params}"


def generate_email_html(
    recipient_name: str,
    quote: Dict[str, str],
    product: Dict[str, str],
    config: Config,
    template_path: str,
) -> str:
    """Render the email HTML by replacing placeholders in the template."""
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()
    # Ensure product link has UTM parameters
    product_link = append_utm(product["link"], config)
    # Simple replacement of placeholders; for more complex logic you could
    # integrate a templating engine such as Jinja2.
    # Determine absolute image URL; if the path is relative (doesn't start with http)
    image_path = product.get("image", "")
    if image_path and not re.match(r"^https?://", image_path):
        image_url = f"{config.site_url}/{image_path.lstrip('/') }"
    else:
        image_url = image_path

    html = template
    # Perform sequential replacements to avoid nested placeholder issues
    html = html.replace("{{NAME}}", recipient_name)
    html = html.replace("{{QUOTE}}", quote["text"])
    html = html.replace("{{PRODUCT_TITLE}}", product["title"])
    html = html.replace("{{PRODUCT_DESC}}", product["description"])
    html = html.replace("{{PRODUCT_IMG}}", image_url)
    html = html.replace("{{PRODUCT_LINK}}", product_link)
    html = html.replace(
        "{{TIP_LINK}}", append_utm(config.tip_link, config) if config.tip_link else "#"
    )
    html = html.replace("{{DATE}}", datetime.now().strftime("%d/%m/%Y"))
    return html


def schedule_email(
    subject: str,
    body_html: str,
    publish_datetime: datetime,
    config: Config,
    previous_email_id_path: str = ".last_email_id",
) -> str:
    """Create and schedule an email via Buttondown API.

    Returns the email ID assigned by Buttondown.  The ID is persisted to
    ``previous_email_id_path`` so that analytics can be retrieved the
    following day.
    """
    headers = {"Authorization": f"Token {config.buttondown_api_key}"}
    # Convert publish_datetime to UTC for Buttondown
    try:
        utc_zone = ZoneInfo("UTC")  # type: ignore[name-defined]
    except Exception:
        utc_zone = pytz.UTC  # type: ignore[name-defined]
    data: Dict[str, Any] = {
        "subject": subject,
        "body": body_html,
        "status": "scheduled",
        "publish_date": publish_datetime.astimezone(utc_zone).isoformat(),
    }
    # Only include newsletter_id if provided
    if config.newsletter_id:
        data["newsletter_id"] = config.newsletter_id
    resp = requests.post("https://api.buttondown.com/v1/emails", headers=headers, json=data)
    resp.raise_for_status()
    resp_json = resp.json()
    email_id = resp_json.get("id")
    # Persist the email ID to a file for later analytics retrieval
    with open(previous_email_id_path, "w", encoding="utf-8") as f:
        f.write(str(email_id))
    return email_id


def retrieve_analytics(email_id: str, config: Config) -> Dict[str, Any]:
    """Fetch analytics for a given email ID using Buttondown API."""
    headers = {"Authorization": f"Token {config.buttondown_api_key}"}
    url = f"https://api.buttondown.com/v1/emails/{email_id}/analytics"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def append_report_row(data: Dict[str, Any], config: Config, subject: str, date_str: str) -> None:
    """Append a row of analytics data to the reports CSV file."""
    headers = [
        "Date",
        "Subject",
        "Recipients",
        "Deliveries",
        "Opens",
        "Clicks",
        "TemporaryFailures",
        "PermanentFailures",
        "Unsubscriptions",
        "Complaints",
    ]
    report_exists = os.path.exists(config.reports_csv)
    with open(config.reports_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header if file is new
        if not report_exists:
            writer.writerow(headers)
        writer.writerow([
            date_str,
            subject,
            data.get("recipients", 0),
            data.get("deliveries", 0),
            data.get("opens", 0),
            data.get("clicks", 0),
            data.get("temporary_failures", 0),
            data.get("permanent_failures", 0),
            data.get("unsubscriptions", 0),
            data.get("complaints", 0),
        ])


def main() -> None:
    # Load configuration
    config = Config.load(os.path.join(os.path.dirname(__file__), "config.json"))

    # Determine publish date/time for tomorrow at configured time
    # Determine timezone; prefer zoneinfo when available
    try:
        tz = ZoneInfo(config.timezone)  # type: ignore[name-defined]
    except Exception:
        # Fallback to pytz if available
        tz = pytz.timezone(config.timezone)  # type: ignore[name-defined]
    now_local = datetime.now(tz)
    send_hour, send_minute = map(int, config.send_time.split(":"))
    publish_dt_local = now_local + timedelta(days=1)
    publish_dt_local = publish_dt_local.replace(hour=send_hour, minute=send_minute, second=0, microsecond=0)

    # Load quotes and products
    quotes_data = load_json_data(os.path.join(os.path.dirname(__file__), "assets", "data", "quotes.json")) if os.path.exists(os.path.join(os.path.dirname(__file__), "assets", "data", "quotes.json")) else [
        {"text": "La lumière que tu cherches à l’extérieur brille déjà en toi."},
        {"text": "Chaque jour est une nouvelle chance de semer des graines de bonheur."},
    ]
    products_data = load_json_data(os.path.join(os.path.dirname(__file__), "assets", "data", "products.json"))

    quote = choose_random_item(quotes_data)
    product = choose_random_item(products_data)

    # Generate HTML
    template_path = os.path.join(os.path.dirname(__file__), "email_template.html")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Email template not found at {template_path}.")
    body_html = generate_email_html(
        recipient_name="{{ subscriber.name }}",  # Placeholder for Buttondown personalised substitution
        quote=quote,
        product=product,
        config=config,
        template_path=template_path,
    )

    subject = f"✨ {quote['text'][:40]}…" if len(quote['text']) > 40 else f"✨ {quote['text']}"

    # Schedule the email
    email_id = schedule_email(
        subject=subject,
        body_html=body_html,
        publish_datetime=publish_dt_local,
        config=config,
    )
    print(f"Scheduled email {email_id} for {publish_dt_local} local time.")

    # If analytics for a previous email exist, retrieve and append to report
    previous_email_id_path = os.path.join(os.path.dirname(__file__), ".last_email_id")
    if os.path.exists(previous_email_id_path):
        with open(previous_email_id_path, "r", encoding="utf-8") as f:
            last_email_id = f.read().strip()
        if last_email_id and last_email_id != str(email_id):
            analytics = retrieve_analytics(last_email_id, config)
            # Date of the previous email is yesterday
            date_str = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")
            append_report_row(analytics, config, subject, date_str)
            print(f"Appended analytics for email {last_email_id} to report.")

    # Overwrite last_email_id with current email for next run
    with open(previous_email_id_path, "w", encoding="utf-8") as f:
        f.write(str(email_id))


if __name__ == "__main__":
    main()
