export default async function bifrostPlugin(_input, _options) {
    return {
        event: async (input) => {
            try {
                if (input.event.type === "session.created") {
                    console.log("[bifrost] session created:", input.event.properties.info);
                }
            }
            catch (err) {
                console.warn("[bifrost] event hook error (non-fatal):", err);
            }
        },
        "tool.execute.before": async (input, _output) => {
            try {
                console.log("[bifrost] tool.execute.before:", input.tool, "session:", input.sessionID);
                // Wave 5: relay to classifier via MCP — pass through unchanged for now
            }
            catch (err) {
                console.warn("[bifrost] tool.execute.before error (non-fatal):", err);
            }
        },
        "permission.ask": async (_input, output) => {
            try {
                output.status = "ask";
                // Wave 5: delegate to permission classifier
            }
            catch (err) {
                console.warn("[bifrost] permission.ask error (non-fatal):", err);
            }
        },
        "experimental.session.compacting": async (input, output) => {
            try {
                console.log("[bifrost] session compacting:", input.sessionID);
                // Wave 2.3: trigger auto-save before compaction
                output.context = [];
            }
            catch (err) {
                console.warn("[bifrost] experimental.session.compacting error (non-fatal):", err);
            }
        },
    };
}
//# sourceMappingURL=index.js.map