from __future__ import annotations

import asyncio
from html import escape

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="Legacy Bank Operations Demo")

MEMBERS = {
    "12345": {"name": "John Demo", "checking": "1245.60", "savings": "4621.77"},
    "22222": {"name": "Maria Sample", "checking": "880.15", "savings": "9910.05"},
    "55555": {"name": "Slow Loading", "checking": "50.00", "savings": "300.00"},
    "70000": {"name": "Restricted Demo", "checking": "75.00", "savings": "510.25"},
    "88888": {"name": "Session Demo", "checking": "10.00", "savings": "90.00"},
}

STYLE = """
body { font-family: Arial, sans-serif; background:#ece9d8; color:#111; margin:0; }
.shell { width:760px; margin:30px auto; border:2px solid #666; background:#f7f4df; }
.header { background:#18365f; color:white; padding:12px 16px; font-weight:bold; }
.content { padding:18px; }
table { border-collapse:collapse; width:100%; background:white; }
td, th { border:1px solid #777; padding:8px; text-align:left; }
label { font-weight:bold; }
input { padding:6px; width:240px; }
button, .button { padding:7px 12px; background:#ddd; border:1px solid #555; color:#111; cursor:pointer; text-decoration:none; }
.notice { border:1px solid #a77; background:#fff3f3; padding:12px; margin:12px 0; }
.dialog { position:fixed; left:50%; top:25%; transform:translateX(-50%); width:360px; border:2px solid #333; background:white; padding:16px; box-shadow:0 5px 30px #555; }
.small { font-size:12px; color:#555; }
"""


def page(title: str, body: str) -> str:
    return f"""<!doctype html><html><head><title>{escape(title)}</title><style>{STYLE}</style></head>
<body><div class="shell"><div class="header">Legacy Bank Operations Console</div><div class="content">{body}</div></div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return page(
        "Member Search",
        """
        <h2>Member Search</h2>
        <form action="/member" method="get">
          <table>
            <tr><td><label for="mid">Member ID</label></td><td><input id="mid" name="member_id" autocomplete="off"></td></tr>
            <tr><td colspan="2"><button type="submit">Search Member</button></td></tr>
          </table>
        </form>
        <p class="small">Demo IDs: 12345 success, 99999 not found, 55555 transient dialog, 70000 permission handoff, 88888 session expiry.</p>
        """,
    )


@app.get("/member", response_class=HTMLResponse)
async def member(member_id: str = Query(...)) -> str:
    member_id = member_id.strip()
    if member_id == "99999" or member_id not in MEMBERS:
        return page(
            "Member Not Found",
            f"""
            <h2>Search Result</h2>
            <div class="notice" data-business-outcome="MEMBER_NOT_FOUND">No member exists for identifier <strong>{escape(member_id)}</strong>.</div>
            <a class="button" href="/">Return to Search</a>
            """,
        )

    if member_id == "55555":
        await asyncio.sleep(0.25)

    m = MEMBERS[member_id]
    special = ""
    if member_id == "55555":
        special = """
        <div id="recoverable-dialog" class="dialog" role="dialog" aria-label="Daily notice">
          <strong>Daily operations notice</strong><p>This known interstitial can be dismissed safely.</p>
          <button id="dismiss-dialog" onclick="document.getElementById('recoverable-dialog').remove()">Dismiss</button>
        </div>
        """
    elif member_id == "70000":
        special = """
        <div id="permission-required" class="notice" data-intervention="PERMISSION_REQUIRED">
          Permission denied for automated access. Operator approval is required.
          <button id="operator-override" onclick="this.parentElement.setAttribute('data-resolved','true'); this.parentElement.innerHTML='Operator override recorded. Automation may resume.'">Operator Override</button>
        </div>
        """
    elif member_id == "88888":
        special = """
        <div id="session-expired" class="notice" data-recoverable="SESSION_EXPIRED">
          Session expired.
          <button id="restore-session" onclick="this.parentElement.remove()">Restore Demo Session</button>
        </div>
        """

    return page(
        "Member Detail",
        f"""
        <h2>Member Detail</h2>
        {special}
        <table>
          <tr><th>Member ID</th><td id="member-id-value">{escape(member_id)}</td></tr>
          <tr><th>Name</th><td>{escape(m['name'])}</td></tr>
          <tr><th>Checking</th><td>${m['checking']}</td></tr>
          <tr><th>Savings</th><td>${m['savings']}</td></tr>
        </table>
        <p><a class="button" href="/member/{escape(member_id)}/savings">View Savings</a></p>
        <p><a class="button" data-risk="risky" href="/member/{escape(member_id)}/open-sub-account">Open Sub-Account</a></p>
        """,
    )


@app.get("/member/{member_id}/savings", response_class=HTMLResponse)
async def savings(member_id: str) -> str:
    m = MEMBERS.get(member_id)
    if not m:
        return page("Member Not Found", '<div data-business-outcome="MEMBER_NOT_FOUND">No member exists.</div>')
    return page(
        "Savings Account",
        f"""
        <h2>Savings Account</h2>
        <table>
          <tr><th>Member ID</th><td id="savings-member-id">{escape(member_id)}</td></tr>
          <tr><th>Current Savings Balance</th><td id="savings-balance">{m['savings']}</td></tr>
        </table>
        <a class="button" href="/member?member_id={escape(member_id)}">Back to Member</a>
        """,
    )


@app.get("/member/{member_id}/open-sub-account", response_class=HTMLResponse)
async def open_sub_account(member_id: str) -> str:
    return page(
        "Sub-Account Review",
        f"""
        <h2>Sub-Account Review</h2>
        <div class="notice" data-risk-gate="IRREVERSIBLE">Creating an account is a risky operation. Human approval is required before confirmation.</div>
        <table><tr><th>Member ID</th><td>{escape(member_id)}</td></tr><tr><th>Type</th><td>Savings Sub-Account</td></tr></table>
        <button disabled>Confirm Creation</button>
        """,
    )


def main() -> None:
    uvicorn.run("app.demo:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
