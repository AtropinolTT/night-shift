# bifrost-fusion-provider-fix — Plan Draft

## Metadata
- **intent**: CLEAR
- **review_required**: false
- **status**: exploring
- **slug**: bifrost-fusion-provider-fix

## Request
"Full plan" — redesign bifrost fusion to use OpenCode's configured providers instead of the companion managing API keys independently. Follows from diagnosis: the companion (Python MCP server) is a separate process with zero access to OpenCode's auth system; `_get_opencode_api_keys()` searches `opencode.json` for API keys but OpenCode stores them internally via `auth.set()`.

## Key Findings (from exploration)
- OpenCode plugin SDK (`@opencode-ai/sdk`) provides `client.session.prompt()` which sends prompts through OpenCode's provider system (handles all auth internally)
- `client.provider.list()` enumerates configured providers
- `client.session.create()` / `.prompt()` / `.delete()` can create temp sessions for model calls
- OpenCode stores API keys internally via `auth.set({providerID, auth: {type:"api", key:"..."}})`, NOT in `opencode.json`
- The credential table at `~/.local/share/opencode/opencode.db` is empty (no stored keys)
- Companion (FastMCP Python) cannot access OpenCode's RPC-based auth system

## Owner-Decision Forks

### Fork 1: Architecture model for model calls
**Why this forks the plan**: determines which component owns LLM interaction, changes file list and complexity.

**Option A: Plugin-bridge (RECOMMENDED)** — Plugin (TypeScript, inside OpenCode) makes all model calls via `client.session.prompt()`. Companion receives raw responses and only does synthesis. Cleanest separation of concerns. Companion never touches API keys. Requires refactoring both plugin and companion.

**Option B: Companion reads from OpenCode credential store** — Keep companion making API calls, but point it at wherever OpenCode stores the DeepSeek API key. Simpler plugin change, but fragile (depends on internal OpenCode storage format), and the credential store appears empty/not populated.

**Option C: Plugin-side dispatch + companion-side synthesis with new MCP tool** — Plugin dispatches prompts to models via OpenCode SDK, collects responses, sends them to a new `fusion_synthesize` MCP tool on the companion. Companion only runs the synthesis prompt (which also needs a model call through OpenCode — handled by plugin too, or keep a lightweight synthesis in companion).

### Fork 2: Synthesis model call
**Why**: the synthesis step also calls a model. Should this move to the plugin too, or stay in the companion?
- **Option A**: Plugin also calls the synthesis model (via OpenCode SDK), companion becomes a pure text-merge function
- **Option B**: Companion still calls the synthesis model using the key fed from plugin
- **Option C (RECOMMENDED)**: Plugin calls ALL models including synthesis. Companion receives pre-fetched responses + synthesis, or becomes purely a formatting/formula function. Most correct, removes all API key dependency from companion.
