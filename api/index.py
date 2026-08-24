import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler

# Add root directory to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import bot
import supabase_db

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Abyssinia Market Bot ? Status</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 36px; max-width: 540px; width: 100%; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5); text-align: center; }
        .badge { display: inline-flex; align-items: center; gap: 8px; background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid #22c55e; border-radius: 9999px; padding: 6px 16px; font-size: 0.875rem; font-weight: 600; margin-bottom: 20px; }
        .badge-dot { width: 8px; height: 8px; background: #22c55e; border-radius: 50%; }
        h1 { font-size: 1.75rem; font-weight: 700; margin-bottom: 12px; color: #fff; }
        p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; margin-bottom: 24px; }
        .links { display: flex; flex-direction: column; gap: 12px; }
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; background: #3b82f6; color: #fff; text-decoration: none; padding: 12px 20px; border-radius: 10px; font-weight: 600; }
        .btn:hover { background: #2563eb; }
        .btn-outline { background: transparent; border: 1px solid #475569; color: #cbd5e1; }
        .btn-outline:hover { background: #334155; color: #fff; }
        .footer { margin-top: 24px; font-size: 0.8rem; color: #64748b; }
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">
            <span class="badge-dot"></span>
            Serverless Webhook Active
        </div>
        <h1>Abyssinia Market Bot</h1>
        <p>Your Telegram automated digital store bot is running online on Vercel Serverless.</p>
        <div class="links">
            <a href="https://t.me/abysinnia_bot" class="btn" target="_blank">Open Bot in Telegram (@abysinnia_bot)</a>
            <a href="/api/set_webhook" class="btn btn-outline">Sync Telegram Webhook</a>
            <a href="/api/sync_supabase" class="btn btn-outline">Sync Data with Supabase</a>
            <a href="https://t.me/abyssinia_botlogs" class="btn btn-outline" target="_blank">Open Logs Group (@abyssinia_botlogs)</a>
        </div>
        <div class="footer">
            Webhook Endpoint: <code>/api/webhook</code> &bull; Powered by Vercel
        </div>
    </div>
</body>
</html>"""

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url_path = self.path.split('?')[0]

        if url_path in ("/api/set_webhook", "/set_webhook"):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                hook_url = "https://abysinia-market.vercel.app/api/webhook"
                res = loop.run_until_complete(bot.api_call("setWebhook", {
                    "url": hook_url,
                    "allowed_updates": ["message", "callback_query"],
                    "drop_pending_updates": False
                }))
                loop.run_until_complete(bot.set_bot_commands())
                loop.run_until_complete(bot.close_session())
            finally:
                loop.close()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "webhook_set": res,
                "target_url": hook_url
            }).encode('utf-8'))
            return

        elif url_path in ("/api/get_webhook", "/get_webhook"):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                res = loop.run_until_complete(bot.api_call("getWebhookInfo"))
                loop.run_until_complete(bot.close_session())
            finally:
                loop.close()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        elif url_path in ("/api/sync_supabase", "/sync_supabase"):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sync_res = loop.run_until_complete(supabase_db.supabase_sync_all_from_local())
            finally:
                loop.close()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "sync_results": sync_res
            }).encode('utf-8'))
            return

        # Default Landing Page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))

    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            if not body:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
                return

            update = json.loads(body.decode('utf-8'))

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(bot.db_init())
                loop.run_until_complete(bot.process_update(update))
                loop.run_until_complete(bot.close_session())
            finally:
                loop.close()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception as ex:
            bot.logger.error(f"[Webhook POST] Error: {ex}", exc_info=True)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(ex)}).encode('utf-8'))
