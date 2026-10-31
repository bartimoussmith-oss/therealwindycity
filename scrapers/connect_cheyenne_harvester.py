#!/usr/bin/env python3
import argparse, requests, re
from granicus_harvester import harvest_and_ingest

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://connectcheyenne.org/")
    args = parser.parse_args()
    # Leverages the same SHA-512 tamper-detection engine against Connect Cheyenne's DOM
    harvest_and_ingest(args.url, "Connect_Cheyenne", historical=True)
