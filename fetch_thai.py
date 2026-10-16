"""Run on the home PC (Windows Task Scheduler): fetch Thai fund NAVs + gold prices,
push them encrypted to GitHub, sync the portfolio secret, then rebuild the dashboard.

Finnomena and goldtraders.or.th block GitHub's servers, so this part can't run on Actions.
"""
import datetime as dt
import json
import subprocess
import sys

import build

REPO = "sutint/market-dashboard"


def run(*cmd, **kw):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=build.ROOT, check=True, **kw)


def main():
    print(f"=== {dt.datetime.now(build.BKK):%Y-%m-%d %H:%M}")
    portfolio_text = (build.ROOT / "portfolio.json").read_text(encoding="utf-8")
    portfolio = json.loads(portfolio_text)

    thai = build.fetch_thai_live(portfolio)
    missing = [f["code"] for f in portfolio.get("funds", []) if not thai["funds"].get(f["code"], {}).get("navs")]
    if missing:
        print(f"  ! no NAV for: {', '.join(missing)}")
    if not thai["gold"]:
        print("  ! no gold price")
    if len(missing) == len(portfolio.get("funds", [])) and not thai["gold"]:
        sys.exit("Nothing fetched - keeping the previous data")
    build.save_thai_cache(thai)

    run("git", "add", "data/thai.enc.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=build.ROOT).returncode:
        run("git", "commit", "-q", "-m", "Update Thai fund and gold data")
    run("git", "pull", "-q", "--rebase")
    run("git", "push", "-q")

    # Keep the portfolio secret in sync with the local portfolio.json
    # Pass UTF-8 bytes: Windows would otherwise encode the Thai text in its ANSI codepage
    run("gh", "secret", "set", "PORTFOLIO_JSON", "-R", REPO, input=portfolio_text.encode("utf-8"))
    run("gh", "workflow", "run", "daily.yml", "-R", REPO)
    print("done")


if __name__ == "__main__":
    main()
