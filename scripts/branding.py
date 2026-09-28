#!/usr/bin/env python3
"""Shared branding for every page: logo/favicon, the top tab switcher, theme.

Kept in one place so swapping the logo or adding a tab updates all pages at once.
"""
import base64
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def posthog():
    """PostHog analytics snippet for every page's <head>.

    Enabled by a committed `posthog.txt` at the repo root (same pattern as
    worker_url.txt): line 1 = the project API key (phc_...), optional line 2 =
    the api_host (defaults to the US cloud). No file -> empty string, no
    analytics. The key is the client-side "public" key — it only lets browsers
    SEND events, so committing it is fine (it ships in the page either way).
    """
    p = f"{_ROOT}/posthog.txt"
    if not os.path.exists(p):
        return ""
    lines = [l.strip() for l in open(p) if l.strip()]
    key = lines[0]
    host = lines[1] if len(lines) > 1 else "https://us.i.posthog.com"
    return (
        '<script>'
        '!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a)'
        '{function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function()'
        '{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script"))'
        '.type="text/javascript",p.crossOrigin="anonymous",p.async=!0,'
        'p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",'
        '(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;'
        'for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t)'
        '{var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},'
        'u.people.toString=function(){return u.toString(1)+".people (stub)"},'
        'o="init capture register register_once register_for_session unregister '
        'unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled '
        'reloadFeatureFlags on onFeatureFlags onSessionId identify setPersonProperties '
        'group resetGroups reset get_distinct_id getGroups get_session_id '
        'get_session_replay_url alias set_config startSessionRecording stopSessionRecording '
        'captureException opt_in_capturing opt_out_capturing has_opted_in_capturing '
        'has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)'
        'g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);'
        f'posthog.init("{key}",{{api_host:"{host}",defaults:"2025-05-24"}})'
        '</script>'
    )

# Logo: a "nerd" basketball — a basketball head wearing thick nerd glasses,
# with eyes, a smile and buck teeth. Used for both the browser-tab icon
# (favicon, as a data URI) and the header logo (inlined). One source.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<circle cx="50" cy="50" r="47" fill="#ec8b2c"/>'
    '<g fill="none" stroke="#20242c" stroke-width="2.4" stroke-linecap="round">'
    '<circle cx="50" cy="50" r="47"/>'
    '<path d="M50 3V97"/>'
    '<path d="M7 29Q50 45 93 29"/>'
    '<path d="M7 71Q50 55 93 71"/>'
    '</g>'
    '<circle cx="31" cy="47" r="4" fill="#20242c"/>'
    '<circle cx="69" cy="47" r="4" fill="#20242c"/>'
    '<g fill="none" stroke="#141821" stroke-width="5">'
    '<rect x="15" y="33" width="32" height="28" rx="9"/>'
    '<rect x="53" y="33" width="32" height="28" rx="9"/>'
    '<path d="M47 42h6" stroke-linecap="round"/>'
    '<path d="M15 43L4 39" stroke-width="4" stroke-linecap="round"/>'
    '<path d="M85 43L96 39" stroke-width="4" stroke-linecap="round"/>'
    '</g>'
    '<g stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" opacity="0.85">'
    '<path d="M20 40h7"/><path d="M58 40h7"/>'
    '</g>'
    '<path d="M33 68Q50 78 67 68" fill="none" stroke="#20242c" '
    'stroke-width="3.6" stroke-linecap="round"/>'
    '<g fill="#ffffff" stroke="#20242c" stroke-width="1.4">'
    '<rect x="43" y="73" width="6.6" height="10" rx="1.8"/>'
    '<rect x="50.4" y="73" width="6.6" height="10" rx="1.8"/>'
    '</g>'
    '</svg>'
)
FAVICON = base64.b64encode(LOGO_SVG.encode()).decode()
LOGO_INLINE = LOGO_SVG.replace('<svg ', '<svg width="28" height="28" ', 1)

SITE_ROOT = "https://slnstatbook.com"
TABS = [("SLN", "/"), ("NDL", "/ndl/"), ("Records", "/records/"), ("Teams", "/teams/")]
# The Data Field Guide lives in page footers (deliberately not a header tab)
GUIDE_LINK = '<a href="https://slnstatbook.com/guide/">📖 Data Field Guide</a>'


def switcher(active):
    """Top-of-page tab switcher. `active` is one of the TAB names."""
    links = "".join(
        f'<a href="{SITE_ROOT}{path}" class="lg{" on" if name == active else ""}">{name}</a>'
        for name, path in TABS)
    return f'<span class="switch">{links}</span>'


SWITCH_CSS = """
  header.top nav{margin-left:auto;color:#aeb7c6;font-size:13px;display:flex;align-items:center}
  .switch{display:inline-flex;border:1px solid #3a4354;border-radius:8px;overflow:hidden}
  .switch .lg{padding:6px 16px;color:#aeb7c6;font-weight:800;font-size:13px;letter-spacing:.4px}
  .switch .lg:hover{background:#232b3a;text-decoration:none;color:#fff}
  .switch .lg.on{background:var(--accent);color:#fff}
"""
