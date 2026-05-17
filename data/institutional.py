"""L1-5: 13-F institutional holdings for 9 tracked hedge funds."""
import logging
import os
import time
from datetime import datetime

import requests

from .db import get_conn
from .sec_data import HEADERS, RATE_LIMIT_SLEEP

logger = logging.getLogger(__name__)

TRACKED_FUNDS = {
    "Citadel":          "0001423053",
    "Point72":          "0001603466",
    "Bridgewater":      "0001350694",
    "Tiger Global":     "0001167483",
    "Third Point":      "0001040273",
    "Berkshire Hathaway": "0001067983",
    "Appaloosa":        "0001070154",
    "Baupost":          "0000876611",
    "Pershing Square":  "0001336528",
}

EDGAR_API = "https://data.sec.gov"


def _get(url: str) -> dict | None:
    try:
        time.sleep(RATE_LIMIT_SLEEP)
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("13-F GET %s: %s", url, e)
        return None


def _parse_13f(cik: str, fund_name: str) -> list[dict]:
    data = _get(f"{EDGAR_API}/submissions/CIK{cik}.json")
    if not data:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])

    acc_13f, date_13f = None, None
    for f, acc, d in zip(forms, accessions, dates):
        if "13F-HR" in f:
            acc_13f, date_13f = acc, d
            break

    if not acc_13f:
        logger.debug("No 13-F found for %s", fund_name)
        return []

    acc_clean = acc_13f.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/{cik}/{acc_clean}/{acc_13f}-index.htm"

    try:
        time.sleep(RATE_LIMIT_SLEEP)
        r = requests.get(index_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        xml_link = None
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "infotable" in href.lower() and href.endswith(".xml"):
                xml_link = f"https://www.sec.gov{href}" if href.startswith("/") else href
                break

        if not xml_link:
            return []

        time.sleep(RATE_LIMIT_SLEEP)
        xml_r = requests.get(xml_link, headers=HEADERS, timeout=60)
        xml_r.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_r.text)
        ns = "{http://www.sec.gov/edgar/document/thirteenf/informationTable}"

        holdings = []
        for entry in root.findall(f"{ns}infoTable"):
            name_el = entry.find(f"{ns}nameOfIssuer")
            cusip_el = entry.find(f"{ns}cusip")
            val_el = entry.find(f"{ns}value")
            shares_el = entry.find(f"{ns}sshPrnamt")
            ticker_el = entry.find(f"{ns}ticker")

            try:
                holdings.append({
                    "fund_name": fund_name,
                    "ticker": ticker_el.text.strip() if ticker_el is not None else name_el.text.strip()[:10],
                    "shares_held": float(shares_el.text) * 1000 if shares_el is not None else 0,
                    "market_value": float(val_el.text) * 1000 if val_el is not None else 0,
                    "report_date": date_13f,
                    "fetched_at": datetime.utcnow().isoformat(),
                })
            except Exception:
                continue

        logger.info("13-F %s: %d holdings (report date %s)", fund_name, len(holdings), date_13f)
        return holdings

    except Exception as e:
        logger.warning("13-F parse %s: %s", fund_name, e)
        return []


def refresh_institutional(skip: bool = False) -> dict:
    if skip:
        return {"skipped": True}

    conn = get_conn()
    summary = {"funds_done": 0, "holdings": 0, "errors": []}

    for fund_name, cik in TRACKED_FUNDS.items():
        try:
            holdings = _parse_13f(cik, fund_name)
            if not holdings:
                continue

            # Get prior quarter's data for net change
            report_date = holdings[0]["report_date"]
            prior = {}
            prior_rows = conn.execute(
                """SELECT ticker, shares_held FROM institutional_holdings
                   WHERE fund_name=? AND report_date < ? ORDER BY report_date DESC""",
                (fund_name, report_date),
            ).fetchall()
            for t, s in prior_rows:
                if t not in prior:
                    prior[t] = s

            for h in holdings:
                net = h["shares_held"] - prior.get(h["ticker"], 0)
                conn.execute(
                    """INSERT OR REPLACE INTO institutional_holdings
                       (fund_name, ticker, shares_held, market_value, report_date,
                        prior_shares, net_change, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (h["fund_name"], h["ticker"], h["shares_held"], h["market_value"],
                     h["report_date"], prior.get(h["ticker"]), net, h["fetched_at"]),
                )

            conn.commit()
            summary["funds_done"] += 1
            summary["holdings"] += len(holdings)

        except Exception as e:
            logger.warning("Institutional %s: %s", fund_name, e)
            summary["errors"].append(f"{fund_name}: {e}")

    conn.close()
    return summary


def get_institutional_data(conn, ticker: str) -> dict:
    """Return aggregated institutional metrics for a ticker."""
    rows = conn.execute(
        """SELECT fund_name, shares_held, market_value, report_date, net_change
           FROM institutional_holdings
           WHERE ticker=?
           ORDER BY report_date DESC""",
        (ticker,),
    ).fetchall()

    if not rows:
        return {"num_funds": 0, "net_change": 0, "multi_fund_open": False}

    # Latest report date only
    latest_date = rows[0][3]
    latest = [r for r in rows if r[3] == latest_date]
    num_funds = len(latest)

    # Net change: sum of net_change for latest period
    net_chg = sum(r[4] or 0 for r in latest)

    # Multi-fund open: 3+ funds with positive net_change (new position)
    prior_holders = set()
    prior_rows = conn.execute(
        """SELECT DISTINCT fund_name FROM institutional_holdings
           WHERE ticker=? AND report_date < ?""",
        (ticker, latest_date),
    ).fetchall()
    prior_holders = {r[0] for r in prior_rows}
    new_openers = sum(1 for r in latest if r[0] not in prior_holders and (r[4] or 0) > 0)

    return {
        "num_funds": num_funds,
        "net_change": net_chg,
        "multi_fund_open": new_openers >= 3,
    }
