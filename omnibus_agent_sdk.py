#!/usr/bin/env python3
import os, json, sqlite3, argparse, subprocess
from datetime import datetime, timezone

class PrometheanOmnibusAgent:
    def __init__(self):
        self.db_path = "database/promethean_evidence.db"
        gz = self.db_path + ".gz"  # committed compressed (GitHub's 100 MB limit)
        if os.path.exists(gz) and not os.path.exists(self.db_path):
            import gzip, shutil
            with gzip.open(gz, "rb") as src, open(self.db_path + ".unpacking", "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            os.replace(self.db_path + ".unpacking", self.db_path)

    def status(self):
        counts = {}
        if os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            for t in ["officials", "governance_items", "veracity_audit"]:
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    counts[t] = 0
            conn.close()
        return {
            "status": "Active",
            "db_path": self.db_path,
            "indexed_records": counts,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def harvest(self, url):
        subprocess.run(["python3", "scrapers/granicus_harvester.py", url], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    p_harv = sub.add_parser("harvest-granicus")
    p_harv.add_argument("--url", required=True)
    args = parser.parse_args()
    agent = PrometheanOmnibusAgent()
    if args.command == "status":
        print(json.dumps(agent.status(), indent=2))
    elif args.command == "harvest-granicus":
        agent.harvest(args.url)
