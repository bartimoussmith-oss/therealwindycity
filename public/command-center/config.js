// command-center config — edit this to set your own password hash
// Generate a hash: echo -n "yourpassword" | openssl dgst -sha256
// Then paste the hex digest below as CMD_CENTER_HASH.
// Example: CMD_CENTER_HASH = "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27e34";
window.CMD_CENTER_HASH = null; // null = uses default "windycity"

// GitHub repo for fetching notebook state / triggering runs
window.GITHUB_REPO = "bartimoussmith-oss/therealwindycity";
window.GITHUB_BRANCH = "arena/015895c5-therealwindycity";

// Paths within the repo
window.STATE_DIR = "notebooklm_controller/state";
window.ARTIFACTS_DIR = "notebooklm_controller/artifacts";

// NotebookLM controller workflow (for triggering runs via workflow_dispatch)
window.WORKFLOW_ID = "notebooklm-controller.yml";

// Set to true to show raw JSON debug panel
window.DEBUG = false;
