"""L1-4: SEC EDGAR — 10-K, 10-Q, 8-K, Form 4 insider transactions."""
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import requests

from .db import get_conn

logger = logging.getLogger(__name__)

EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
EDGAR_API = "https://data.sec.gov"
HEADERS = {
    "User-Agent": f"MeridianCapital hedge-fund-system {os.getenv('ANTHROPIC_API_KEY', 'contact@example.com')}",
    "Accept": "application/json",
}
RATE_LIMIT_SLEEP = 0.125  # 8 req/sec = 125ms between requests


def _get(url: str, params: dict = None) -> dict | None:
    try:
        time.sleep(RATE_LIMIT_SLEEP)
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("SEC GET %s: %s", url, e)
        return None


def _ticker_to_cik(ticker: str) -> Optional[str]:
    data = _get("https://efts.sec.gov/LATEST/search-index?q=%22%22&dateRange=custom&startdt=2020-01-01&enddt=2025-01-01&forms=10-K")
    # Use company_tickers.json for reliable mapping
    data = _get(f"{EDGAR_API}/files/company_tickers.json")
    if not data:
        return None
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    return None


def _get_filings(cik: str, form_type: str, count: int = 5) -> list[dict]:
    url = f"{EDGAR_API}/cgi-bin/browse-edgar"
    params = {
        "action": "getcompany",
        "CIK": cik,
        "type": form_type,
        "dateb": "",
        "owner": "include",
        "count": count,
        "output": "atom",
    }
    # Use submissions endpoint instead
    data = _get(f"{EDGAR_API}/submissions/CIK{cik}.json")
    if not data:
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    results = []
    for f, acc, d in zip(forms, accessions, dates):
        if f.strip() == form_type:
            acc_clean = acc.replace("-", "")
            results.append({
                "form": f,
                "accession": acc,
                "date": d,
                "url": f"https://www.sec.gov/Archives/edgar/{cik}/{acc_clean}/",
            })
            if len(results) >= count:
                break
    return results


def _fetch_text_filing(cik: str, accession: str, form_type: str) -> Optional[str]:
    acc_clean = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/{cik}/{acc_clean}/{accession}-index.htm"
    try:
        time.sleep(RATE_LIMIT_SLEEP)
        r = requests.get(index_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "lxml")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".htm") and form_type.replace("-", "").lower() in href.lower():
                doc_url = f"https://www.sec.gov{href}" if href.startswith("/") else href
                time.sleep(RATE_LIMIT_SLEEP)
                doc_r = requests.get(doc_url, headers=HEADERS, timeout=60)
                doc_r.raise_for_status()
                doc_soup = BeautifulSoup(doc_r.text, "lxml")
                return doc_soup.get_text(separator=" ", strip=True)[:100_000]
    except Exception as e:
        logger.debug("Filing text %s %s: %s", cik, accession, e)
    return None


def _parse_form4_xml(xml_text: str, ticker: str) -> list[dict]:
    transactions = []
    try:
        root = ET.fromstring(xml_text)
        ns = ""
        issuer_ticker = ""
        issuer_el = root.find("issuer")
        if issuer_el is not None:
            t_el = issuer_el.find("issuerTradingSymbol")
            issuer_ticker = t_el.text.strip() if t_el is not None else ticker

        owner_el = root.find(".//reportingOwner")
        name, title = "", ""
        if owner_el is not None:
            id_el = owner_el.find("reportingOwnerId")
            if id_el is not None:
                n = id_el.find("rptOwnerName")
                name = n.text.strip() if n is not None else ""
            rel_el = owner_el.find("reportingOwnerRelationship")
            if rel_el is not None:
                t = rel_el.find("officerTitle")
                title = t.text.strip() if t is not None else ""

        is_exec = any(k in title.upper() for k in ["CEO", "CFO", "CHIEF EXECUTIVE", "CHIEF FINANCIAL"])

        for txn in root.findall(".//nonDerivativeTransaction"):
            code_el = txn.find(".//transactionCode")
            shares_el = txn.find(".//transactionShares/value")
            price_el = txn.find(".//transactionPricePerShare/value")
            date_el = txn.find(".//transactionDate/value")
            own_el = txn.find(".//directOrIndirectOwnership/value")

            code = code_el.text.strip() if code_el is not None else ""
            if code not in ("P", "S"):
                continue

            try:
                shares = float(shares_el.text) if shares_el is not None else 0
                price = float(price_el.text) if price_el is not None else 0
                date = date_el.text.strip() if date_el is not None else ""
                own = own_el.text.strip() if own_el is not None else "D"
            except (TypeError, ValueError):
                continue

            transactions.append({
                "ticker": issuer_ticker or ticker,
                "insider_name": name,
                "insider_title": title,
                "transaction_type": "BUY" if code == "P" else "SELL",
                "transaction_code": code,
                "shares": shares,
                "price": price,
                "amount": shares * price,
                "date": date,
                "ownership_type": own,
                "is_ceo_cfo": int(is_exec),
                "fetched_at": datetime.utcnow().isoformat(),
            })
    except ET.ParseError as e:
        logger.debug("Form4 XML parse error: %s", e)
    return transactions


def refresh_sec_filings(tickers: list[str]) -> dict:
    conn = get_conn()
    summary = {"tickers_done": 0, "insider_txns": 0, "errors": []}
    import sys as _sys, pathlib
    _sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from paths import cache_dir as _cache_dir
    cache_path = _cache_dir() / "sec_filings"
    cache_path.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        try:
            cik = _ticker_to_cik(ticker)
            if not cik:
                logger.debug("No CIK for %s", ticker)
                continue

            # Fetch Form 4s (last 180 days)
            cutoff = (datetime.utcnow() - timedelta(days=180)).strftime("%Y-%m-%d")
            form4s = _get_filings(cik, "4", count=40)
            txn_count = 0
            for filing in form4s:
                if filing["date"] < cutoff:
                    break
                acc = filing["accession"]
                acc_clean = acc.replace("-", "")
                xml_url = (
                    f"https://www.sec.gov/Archives/edgar/{cik}/{acc_clean}/{acc}.txt"
                )
                # Try to get XML directly
                try:
                    time.sleep(RATE_LIMIT_SLEEP)
                    r = requests.get(xml_url, headers=HEADERS, timeout=30)
                    if r.status_code == 200:
                        txns = _parse_form4_xml(r.text, ticker)
                        for t in txns:
                            conn.execute(
                                """INSERT OR IGNORE INTO insider_transactions
                                   (ticker, insider_name, insider_title, transaction_type,
                                    transaction_code, shares, price, amount, date,
                                    ownership_type, is_ceo_cfo, filing_url, fetched_at)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (t["ticker"], t["insider_name"], t["insider_title"],
                                 t["transaction_type"], t["transaction_code"], t["shares"],
                                 t["price"], t["amount"], t["date"], t["ownership_type"],
                                 t["is_ceo_cfo"], xml_url, t["fetched_at"]),
                            )
                            txn_count += 1
                except Exception:
                    pass

            if txn_count:
                conn.commit()
            summary["insider_txns"] += txn_count
            summary["tickers_done"] += 1
            logger.info("SEC Form4 %s: %d transactions", ticker, txn_count)

        except Exception as e:
            logger.warning("SEC error %s: %s", ticker, e)
            summary["errors"].append(f"{ticker}: {e}")

    conn.close()
    return summary


def get_insider_transactions(conn, ticker: str, days: int = 90) -> list[dict]:
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT ticker, insider_name, insider_title, transaction_type,
                  transaction_code, shares, price, amount, date,
                  ownership_type, is_ceo_cfo
           FROM insider_transactions
           WHERE ticker=? AND date>=?
           ORDER BY date DESC""",
        (ticker, cutoff),
    ).fetchall()
    cols = ["ticker", "insider_name", "insider_title", "transaction_type",
            "transaction_code", "shares", "price", "amount", "date",
            "ownership_type", "is_ceo_cfo"]
    return [dict(zip(cols, r)) for r in rows]


def detect_cluster_buying(conn, ticker: str, days: int = 30) -> bool:
    """Return True if 3+ insiders have purchased within `days`."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    row = conn.execute(
        """SELECT COUNT(DISTINCT insider_name) FROM insider_transactions
           WHERE ticker=? AND transaction_code='P' AND date>=?""",
        (ticker, cutoff),
    ).fetchone()
    return (row[0] or 0) >= 3
