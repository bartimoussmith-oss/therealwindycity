# Command Center Operator

## Identity and limits
Persistent operator specification for the Wyoming civic-records project. This file is not a provisioned Perplexity Teammate, autonomous LLM agent, hosted service, or proof of deployment. The accompanying Python server is a deterministic local job runner. Its SQLite queue and logs persist across restarts; the server must remain running to execute jobs.

## Start
From the repository root on the machine hosting the records pipeline:

```sh
python3 tools/command_center.py
```

Open http://127.0.0.1:8765 and enter the access token printed in the terminal. Do not publish that token, authentication cookies, logs containing secrets, or NotebookLM storage_state.json. Do not expose this server through a public tunnel. Run only one server instance per state directory. The server is not hosted by GitHub Pages.

The server uses Python's standard library. Individual engine jobs still require their existing dependencies. It runs the selected jurisdiction's configuration using ENGINE_CONFIG_DIR, ENGINE_DATA_DIR, and ENGINE_PUBLIC_DIR. It deliberately does not source arbitrary instance env.sh files; deployments relying on additional environment variables must supply them before starting the server.

## Capabilities
- Select a configured Wyoming jurisdiction.
- Queue init, crawl, work, digest, or a sequential cycle of those four commands.
- Execute one job at a time without a five-minute HTTP request timeout.
- Read the last 64 KB of each job log and durable job history.
- Preserve queued jobs on restart; mark previously running jobs interrupted, not successful.
- Stop a cycle on the first nonzero command exit.

A successful process exit is not evidence of a captured meeting, healthy source, published record, or successful repeat collection. The current engine can exit successfully after individual fetch failures. Source-level verification and publication are separate work. No arbitrary shell endpoint, automatic GitHub pushes, NotebookLM mutation, or automatic public publishing is included. There is no job-cancellation endpoint or automatic retry of interrupted jobs. Stopping the server does not guarantee that an already started child process stops; verify the child before requeueing an interrupted crawl.

## Standing mission
Maintain a source-linked collection-to-publication pipeline without replacing the archive or game. Distinguish configured, reviewed, enabled, fetched, extracted, published, and repeat-verified states. Never count directory pages as functioning reporting operations or navigation pages as meeting records. Require actual logs and live checks before reporting deployment complete.

## Collection policy and next implementation work
The owner's instruction is that robots.txt is not a collection gate. Retain official-source review, request identification, per-host delays, timeouts, size and download limits, and authentication/access-control boundaries. Do not use proxies, CAPTCHA bypasses, or credential workarounds to evade denied access.

The existing engine/ingest.py still enforces robots.txt. This server does not remove that gate or silently override collector functions. A separate reviewed change must remove enforcement in the collector and source-activation validator, update the policy documentation and regression tests, and re-evaluate previously rejected reviewed sources. Do not claim Governor or Natrona enabled without checking their actual source configuration and test output.

## NotebookLM blocker
The supplied Termux log reports no compatible Playwright distribution. Do not repeatedly downgrade notebooklm-py or retry the same browser installation there. Diagnose authentication on a supported browser host separately; never store Google session files in the repository. The Command Center does not fix or test NotebookLM authentication.

## Acceptance checks before production claims
1. Compile the server and run authenticated HTTP smoke tests, including wrong-token and cross-origin rejection.
2. Test queue restart recovery using temporary state and isolated fixture data.
3. Validate an actual jurisdiction configuration, run an approved collection, inspect capture evidence, and repeat successfully.
4. Keep logs and credentials outside public/.
5. Configure and verify a host-specific service manager if automatic startup is required. No service installation is performed by this commit.

This initial implementation has not yet been executed on the owner's host.
