
const GEMINI_MODELS = ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-2.5-flash"];

export default async (req) => {
  const gKey = process.env.GOOGLE_AI_API_KEY || "";
  const aKey = process.env.ANTHROPIC_API_KEY || "";
  const configured = !!(gKey || aKey);

  if (req.method === "GET") {
    return Response.json({ configured });
  }
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }
  if (!configured) {
    return Response.json({ error: "No server key configured" }, { status: 503 });
  }

  let body;
  try { body = await req.json(); } catch (e) {
    return Response.json({ error: "Bad request" }, { status: 400 });
  }
  const system = String(body.system || "").slice(0, 20000);
  const user = String(body.user || "").slice(0, 20000);
  if (!user) return Response.json({ error: "Missing prompt" }, { status: 400 });

  try {
    if (aKey) {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "content-type": "application/json", "x-api-key": aKey, "anthropic-version": "2023-06-01" },
        body: JSON.stringify({ model: "claude-sonnet-5", max_tokens: 4000, system, messages: [{ role: "user", content: user }] }),
      });
      if (!r.ok) return Response.json({ error: "Claude error (" + r.status + ")" }, { status: 502 });
      const d = await r.json();
      return Response.json({ text: (d.content && d.content[0] && d.content[0].text) || "" });
    }
    let lastStatus = 0;
    for (const model of GEMINI_MODELS) {
      const r = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + encodeURIComponent(gKey),
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: user }] }] }),
        },
      );
      if (r.ok) {
        const d = await r.json();
        const parts = (d.candidates && d.candidates[0] && d.candidates[0].content && d.candidates[0].content.parts) || [];
        return Response.json({ text: parts.map((p) => p.text || "").join("") });
      }
      lastStatus = r.status;
      if (r.status !== 404) break;
    }
    return Response.json({ error: "Google AI error (" + lastStatus + ")" }, { status: 502 });
  } catch (e) {
    return Response.json({ error: "Upstream failure" }, { status: 502 });
  }
};
