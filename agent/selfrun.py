#!/usr/bin/env python3
"""Launcher used by the install scripts (`wyagent`).

Works from any working directory: it finds the repo from WY_REPO, from its own
location, or by walking up from the current directory — then runs the CLI.
Kept dependency-free and side-effect-free so it is safe to symlink anywhere.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def find_repo() -> Path | None:
    env = os.environ.get("WY_REPO")
    if env and (Path(env) / "agent" / "cli.py").exists():
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for cand in (here.parent.parent, *here.parents):
        if (cand / "agent" / "cli.py").exists():
            return cand
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / "agent" / "cli.py").exists():
            return cand
    return None


def main() -> int:
    repo = find_repo()
    if repo is None:
        print("windycity-agent: cannot find the repo.\n"
              "Set WY_REPO=/path/to/therealwindycity and run again.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    from agent.cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
