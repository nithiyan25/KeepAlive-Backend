import os
from dotenv import load_dotenv

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDER_EMAIL     = os.getenv("SENDER_EMAIL", "")
ADMIN_EMAIL      = os.getenv("ADMIN_EMAIL", "")
FRONTEND_URL     = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ── Internal sender ───────────────────────────────────────────────────────────

def _send(to: str, subject: str, html: str) -> bool:
    if not SENDGRID_API_KEY or not SENDER_EMAIL:
        print(f"[EMAIL] SendGrid not configured — skipping '{subject}' to {to}")
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        msg  = Mail(from_email=SENDER_EMAIL, to_emails=to, subject=subject, html_content=html)
        resp = SendGridAPIClient(SENDGRID_API_KEY).send(msg)
        print(f"[EMAIL] Sent '{subject}' → {to} (status {resp.status_code})")
        return True
    except Exception as e:
        print(f"[EMAIL] Error sending to {to}: {e}")
        return False


# ── 1. Admin: new signup notification ────────────────────────────────────────

def send_new_signup_notification(user: dict) -> bool:
    """Notify admin that a new user wants access. Includes link to admin panel."""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0a0a0a;padding:30px">
      <div style="max-width:560px;margin:0 auto;background:#111;border:1px solid #222;border-radius:8px;padding:32px">
        <h2 style="color:#00ff88;margin:0 0 4px">New Access Request</h2>
        <p style="color:#555;font-size:12px;margin:0 0 24px">KeepAlive Pinger</p>
        <hr style="border:none;border-top:1px solid #1e1e1e;margin-bottom:20px"/>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
          <tr>
            <td style="color:#444;font-size:11px;letter-spacing:1px;padding:6px 0;width:80px">NAME</td>
            <td style="color:#e0e0e0;font-size:14px">{user['name']}</td>
          </tr>
          <tr>
            <td style="color:#444;font-size:11px;letter-spacing:1px;padding:6px 0">EMAIL</td>
            <td style="color:#e0e0e0;font-size:14px">{user['email']}</td>
          </tr>
        </table>
        <a href="{FRONTEND_URL}/admin"
           style="display:inline-block;background:#00ff88;color:#000;text-decoration:none;
                  padding:10px 24px;border-radius:4px;font-weight:bold;font-size:12px;
                  font-family:monospace;letter-spacing:1px">
          OPEN ADMIN PANEL →
        </a>
        <p style="color:#2a2a2a;font-size:10px;margin-top:24px">
          KeepAlive Pinger — automatic signup notification
        </p>
      </div>
    </body></html>
    """
    return _send(
        ADMIN_EMAIL,
        f"[KeepAlive] New signup: {user['name']} ({user['email']})",
        html,
    )


# ── 2. User: approved ─────────────────────────────────────────────────────────

def send_approval_email(user: dict) -> bool:
    """Tell the user their account has been approved."""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0a0a0a;padding:30px">
      <div style="max-width:560px;margin:0 auto;background:#111;border:1px solid #0f2a1a;border-radius:8px;padding:32px">
        <h2 style="color:#00ff88;margin:0 0 4px">You're approved! 🎉</h2>
        <p style="color:#555;font-size:12px;margin:0 0 24px">KeepAlive Pinger</p>
        <hr style="border:none;border-top:1px solid #1e1e1e;margin-bottom:20px"/>
        <p style="color:#c8c8c8;font-size:14px;line-height:1.8;margin-bottom:28px">
          Hi <strong style="color:#fff">{user['name']}</strong>,<br/><br/>
          Your KeepAlive account has been approved. You can now sign in and start
          adding your free-tier backends to keep them alive automatically.
        </p>
        <a href="{FRONTEND_URL}/login"
           style="display:inline-block;background:#00ff88;color:#000;text-decoration:none;
                  padding:12px 28px;border-radius:4px;font-weight:bold;font-size:12px;
                  font-family:monospace;letter-spacing:1px">
          SIGN IN NOW →
        </a>
        <p style="color:#2a2a2a;font-size:10px;margin-top:28px">
          You received this because you signed up at {FRONTEND_URL}
        </p>
      </div>
    </body></html>
    """
    return _send(user["email"], "[KeepAlive] Your account is approved ✓", html)


# ── 3. User: rejected ─────────────────────────────────────────────────────────

def send_rejection_email(user: dict) -> bool:
    """Tell the user their request was not approved."""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#0a0a0a;padding:30px">
      <div style="max-width:560px;margin:0 auto;background:#111;border:1px solid #2a0f0f;border-radius:8px;padding:32px">
        <h2 style="color:#ff3b3b;margin:0 0 4px">Access Request Update</h2>
        <p style="color:#555;font-size:12px;margin:0 0 24px">KeepAlive Pinger</p>
        <hr style="border:none;border-top:1px solid #1e1e1e;margin-bottom:20px"/>
        <p style="color:#c8c8c8;font-size:14px;line-height:1.8;margin-bottom:12px">
          Hi <strong style="color:#fff">{user['name']}</strong>,<br/><br/>
          Unfortunately your access request for KeepAlive Pinger was not approved
          at this time. If you believe this is a mistake, please contact the administrator.
        </p>
        <p style="color:#2a2a2a;font-size:10px;margin-top:28px">
          You received this because you signed up at {FRONTEND_URL}
        </p>
      </div>
    </body></html>
    """
    return _send(user["email"], "[KeepAlive] Access request update", html)