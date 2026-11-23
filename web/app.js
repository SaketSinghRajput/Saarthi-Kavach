// Placeholder: logs every SSE event. Text is set with textContent only (C5).
const log = document.getElementById("log");
const types = ["call_status", "turn", "detector", "entity", "goal_state", "band", "metrics", "draft", "skill", "policy"];
const es = new EventSource("/api/events");
for (const t of types) {
  es.addEventListener(t, (e) => {
    log.textContent += t + " " + e.data + "\n";
    log.scrollTop = log.scrollHeight;
  });
}
document.getElementById("start").addEventListener("click", async () => {
  const r = await fetch("/api/call/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: document.getElementById("scenario").value, input_mode: "scripted" }),
  });
  log.textContent += "start -> " + r.status + "\n";
});
