#!/usr/bin/env python3
import os, json, argparse, subprocess
from datetime import datetime

class PrometheanOmnibusAgent:
    def __init__(self):
        self.db_path = "database/promethean_evidence.db"
    def status(self):
        return {"status": "Active", "db_path": self.db_path, "timestamp": datetime.utcnow().isoformat()}
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
