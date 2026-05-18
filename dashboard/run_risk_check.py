#!/usr/bin/env python3
"""L5 Entry Point: Meridian Capital Partners — Risk Management."""
import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
logging.basicConfig(
    level=getattr(logging, cfg["logging"]["level"]),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_risk")
AUM = cfg["fund"]["aum_usd"]


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Risk Check")
    parser.add_argument("--stress", action="store_true", help="Run stress tests")
    parser.add_argument("--tail-only", action="store_true", help="Only check tail risk")
    parser.add_argument("--clear-halt", action="store_true", help="Clear KILL_SWITCH halt lock")
    args = parser.parse_args()

    if args.clear_halt:
        from risk.circuit_breakers import clear_halt
        clear_halt()
        return

    from portfolio.state import init_portfolio_tables, get_positions, update_current_prices
    from risk.tail_risk import get_vix, get_credit_spread_zscore, evaluate_tail_risk
    from risk.circuit_breakers import check_circuit_breakers
    from risk.risk_state import update_risk_state, load as load_state

    init_portfolio_tables()
    update_current_prices()

    positions = get_positions()
    weights = {}
    if not positions.empty:
        for _, row in positions.iterrows():
            price = row.get("current_price") or row.get("entry_price", 100)
            weights[row["ticker"]] = row["shares"] * price / AUM

    vix = get_vix()
    cs_z = get_credit_spread_zscore()
    logger.info("VIX: %.1f | Credit spread z: %s", vix,
                f"{cs_z:.2f}" if cs_z is not None else "N/A (no FRED key)")

    # Tail risk
    tail_actions = evaluate_tail_risk(cfg)

    if args.tail_only:
        _print_risk_summary(vix, cs_z, tail_actions, [], [])
        return

    # Circuit breakers (using stored state)
    state = load_state()
    daily_pnl = state.get("daily_pnl", 0.0)
    weekly_pnl = state.get("weekly_pnl", 0.0)
    drawdown = state.get("drawdown", 0.0)
    circuit_actions = check_circuit_breakers(daily_pnl / AUM, weekly_pnl / AUM, drawdown, AUM)

    # Stress tests
    stress_results = []
    if args.stress and weights:
        logger.info("Running stress tests…")
        from risk.stress_test import run_stress_tests
        stress_results = run_stress_tests(weights, AUM)

    # Factor risk model
    portfolio_risk = {}
    if weights:
        scored_path = ROOT / "output" / "scored_universe_latest.csv"
        if scored_path.exists():
            import pandas as pd
            scored = pd.read_csv(scored_path, index_col="ticker")
            from risk.factor_risk_model import build_factor_risk_model, compute_portfolio_risk
            model = build_factor_risk_model(scored)
            if model:
                portfolio_risk = compute_portfolio_risk(weights, model)

    # Update state
    update_risk_state(portfolio_risk, circuit_actions, tail_actions, stress_results, vix, cs_z)

    _print_risk_summary(vix, cs_z, tail_actions, circuit_actions, stress_results, portfolio_risk)


def _print_risk_summary(vix, cs_z, tail, circuit, stress, port_risk=None):
    print("\n" + "=" * 60)
    print("MERIDIAN CAPITAL PARTNERS — RISK STATUS")
    print("=" * 60)
    halt = (Path(__file__).parent / "cache" / "HALT.lock").exists()
    print(f"HALT lock: {'🔴 ACTIVE' if halt else '✅ Clear'}")
    print(f"VIX: {vix:.1f} | Credit Spread Z: {cs_z:.2f if cs_z else 'N/A'}")

    if port_risk:
        print(f"\nPortfolio Risk:")
        print(f"  Total vol:    {port_risk.get('total_vol', 0)*100:.1f}% annualized")
        print(f"  Factor vol:   {port_risk.get('factor_vol', 0)*100:.1f}%")
        print(f"  Specific vol: {port_risk.get('specific_vol', 0)*100:.1f}%")

    if tail:
        print("\nTAIL RISK ACTIONS:")
        for a in tail:
            print(f"  ⚠ {a['message']}")

    if circuit:
        print("\nCIRCUIT BREAKERS:")
        for a in circuit:
            print(f"  🔴 {a['type']}: {a['trigger']} = {a['value']:.2%}")

    if stress:
        print("\nSTRESS TESTS:")
        for s in stress:
            sign = "+" if s["portfolio_return"] > 0 else ""
            print(f"  {s['scenario'][:40]:40} {sign}{s['portfolio_return']*100:.1f}% "
                  f"(${s['portfolio_pnl_usd']:+,.0f})")

    print("=" * 60)


if __name__ == "__main__":
    main()
