// Cloudflare Worker — "Refresh now" relay for the SLN Stat Book.
//
// The public webpage can't safely hold a GitHub token, so this tiny worker
// holds it (as the secret GH_TOKEN) and triggers the repo's Update workflow.
// It refuses to stack a new build if one is already running (anti-spam).
//
// Setup: see REFRESH_BUTTON_SETUP.txt. You paste this into a free Cloudflare
// Worker, add GH_TOKEN as a secret, deploy, and give the worker URL to Claude.

const REPO = "jburns-build/sln-stat-book";
const WORKFLOW = "update.yml";

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });

    const json = (obj, status = 200) =>
      new Response(JSON.stringify(obj), {
        status,
        headers: { ...cors, "Content-Type": "application/json" },
      });

    const api = `https://api.github.com/repos/${REPO}`;
    const gh = (path, opts = {}) =>
      fetch(api + path, {
        ...opts,
        headers: {
          Authorization: `Bearer ${env.GH_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "sln-statbook-refresh",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(opts.headers || {}),
        },
      });

    try {
      // Don't stack builds: if one is queued/running, report that instead.
      const runsRes = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
      if (runsRes.ok) {
        const runs = await runsRes.json();
        const latest = runs.workflow_runs && runs.workflow_runs[0];
        if (latest && (latest.status === "queued" || latest.status === "in_progress")) {
          return json({ ok: true, status: "already_refreshing" });
        }
      }
      // Trigger a fresh build.
      const d = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST",
        body: JSON.stringify({ ref: "main" }),
      });
      if (d.status === 204) return json({ ok: true, status: "triggered" });
      return json({ ok: false, error: `GitHub returned ${d.status}: ${await d.text()}` }, 502);
    } catch (e) {
      return json({ ok: false, error: String(e) }, 500);
    }
  },
};
