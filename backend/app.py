"""
Main FastAPI server.

Endpoints used by the ESP32:
  POST /welcome       -> robot starts the chat (menu: story / count / alphabet)
  POST /process_voice -> receive mic audio, return SUCCESS
  GET  /reply.wav     -> download the spoken reply

Endpoints for parents (digital twin):
  GET  /               -> live dashboard (chats + safety alerts)
  GET  /alerts         -> JSON list of alerts
  POST /alerts/{id}/read
"""

import asyncio
import logging
import traceback
import uuid
import wave

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from backend import config
from backend import database
from backend import ai_services
from backend import features

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("VoiceAssistant")

app = FastAPI(title="Kids Companion Robot")
database.init_db()


def _escape(text: str) -> str:
    """Very small HTML escape so chat text cannot break the dashboard."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page_styles() -> str:
    return """
    body {
        font-family: Segoe UI, Tahoma, sans-serif;
        background: #121214;
        color: #e0e0e0;
        margin: 0;
        padding: 20px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .container {
        width: 100%;
        max-width: 760px;
        background: #1a1a1e;
        border-radius: 12px;
        padding: 20px;
        box-sizing: border-box;
    }
    h1, h2 { margin-top: 0; }
    h1 { color: #4f46e5; text-align: center; }
    h2 { color: #c4b5fd; font-size: 1.1rem; margin-top: 24px; }
    .status-bar {
        text-align: center;
        color: #a7f3d0;
        background: #064e3b;
        padding: 8px;
        border-radius: 6px;
        margin-bottom: 16px;
    }
    .attention-banner {
        display: flex;
        align-items: center;
        gap: 10px;
        background: #3f1515;
        border: 1px solid #ef4444;
        color: #fecaca;
        padding: 12px 14px;
        border-radius: 8px;
        margin-bottom: 16px;
        font-weight: 600;
    }
    .bang {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: #ef4444;
        color: white;
        font-weight: 800;
        font-size: 0.95rem;
    }
    .chat-block, .alert-block {
        background: #26262b;
        padding: 12px 16px;
        margin-bottom: 12px;
        border-radius: 0 8px 8px 0;
    }
    .chat-block { border-left: 4px solid #4f46e5; }
    .chat-block.flagged {
        border-left-color: #ef4444;
        background: #3f1515;
    }
    .chat-block.highlight {
        outline: 2px solid #f87171;
        box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.25);
    }
    a.chat-link {
        color: inherit;
        text-decoration: none;
        display: block;
    }
    a.chat-link:hover .chat-block.flagged {
        filter: brightness(1.12);
        cursor: pointer;
    }
    .click-hint {
        color: #fca5a5;
        font-size: 0.8rem;
        margin-top: 8px;
    }
    .flag-reason { color: #fecaca; font-size: 0.85rem; margin-top: 8px; }
    .alert-block { border-left: 4px solid #f59e0b; background: #3b2a14; }
    .alert-block.severity-high { border-left-color: #ef4444; background: #3f1515; }
    .alert-block.severity-medium { border-left-color: #f59e0b; }
    .alert-block.severity-low { border-left-color: #eab308; }
    .user-msg { color: #60a5fa; margin-bottom: 6px; }
    .ai-msg { color: #34d399; }
    .advice { color: #fde68a; margin-top: 6px; }
    .meta { color: #9ca3af; font-size: 0.8rem; margin-bottom: 6px; }
    .empty { color: #888; text-align: center; }
    .footer { text-align: center; margin-top: 16px; color: #6b7280; font-size: 0.8rem; }
    .back-link {
        display: inline-block;
        margin-bottom: 16px;
        color: #a5b4fc;
        text-decoration: none;
    }
    .back-link:hover { text-decoration: underline; }
    """


@app.post("/welcome")
async def welcome():
    """
    Robot starts with a normal friendly greeting.
    Activity options (story / count / alphabet) are offered later
    only if the child does not choose one.
    """
    try:
        welcome_text = features.start_welcome_menu()
        session_id = features.get_current_session_id()
        await asyncio.to_thread(ai_services.text_to_speech_8bit, welcome_text, config.REPLY_WAV)
        database.save_chat(
            "[session start]",
            welcome_text,
            mode="free",
            session_id=session_id,
        )
        log.info(f"[WELCOME] session={session_id} {welcome_text}")
        return Response(content="SUCCESS", media_type="text/plain")
    except Exception as e:
        detailed = f"Welcome Error: {e}\n{traceback.format_exc()}"
        log.error(detailed)
        return Response(content=detailed, status_code=500, media_type="text/plain")


@app.post("/process_voice")
async def process_voice(request: Request):
    """Full pipeline: audio -> text -> safety -> reply -> TTS -> save for parents."""
    try:
        audio_bytes = await request.body()
        if not audio_bytes or len(audio_bytes) < 100:
            return Response(content="FAIL: empty audio", status_code=400)

        # 1) Save ESP32 raw PCM as a WAV file
        wav_path = config.TEMP_DIR / f"input_{uuid.uuid4().hex}.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_bytes)

        log.info(f"Saved recording: {wav_path} ({len(audio_bytes)} bytes)")

        # 2) Speech to text (Groq Whisper)
        user_text = await asyncio.to_thread(ai_services.speech_to_text, wav_path)
        log.info(f"[STT] Child said: {user_text}")

        # 3) Menu choice or mode switch (story / count / alphabet)
        mode, fixed_reply, used_fixed = features.handle_child_turn(user_text)
        log.info(f"[MODE] {mode} (fixed_reply={used_fixed})")

        # 4) Safety check for parents
        analysis = await asyncio.to_thread(
            features.analyze_sensitive_topic,
            ai_services.groq_client,
            config.GROQ_CHAT_MODEL,
            user_text,
        )

        # 5) Reply: fixed activity starter, otherwise real Groq AI
        if used_fixed:
            ai_reply = fixed_reply
        else:
            ai_reply = await asyncio.to_thread(ai_services.ask_llm, user_text, mode)
            offer = features.consume_activity_offer()
            if offer:
                ai_reply = f"{ai_reply} {offer}"
        log.info(f"[LLM] Reply: {ai_reply}")

        # 6) ElevenLabs TTS for ESP32
        await asyncio.to_thread(ai_services.text_to_speech_8bit, ai_reply, config.REPLY_WAV)

        # 7) Save chat for parents (flagged chats show in red on the twin)
        is_flagged = bool(analysis.get("is_sensitive"))
        session_id = features.get_current_session_id()
        chat_id = database.save_chat(
            user_text,
            ai_reply,
            mode=mode,
            session_id=session_id,
            is_flagged=is_flagged,
            alert_category=analysis.get("category") if is_flagged else None,
            alert_severity=analysis.get("severity") if is_flagged else None,
            alert_summary=analysis.get("summary") if is_flagged else None,
        )
        if is_flagged:
            database.save_alert(
                child_message=user_text,
                category=analysis["category"],
                severity=analysis["severity"],
                summary=analysis["summary"],
                parent_advice=analysis["parent_advice"],
                chat_id=chat_id,
            )
            log.warning(
                f"[PARENT ALERT] {analysis['severity']} / {analysis['category']}: {analysis['summary']}"
            )

        return Response(content="SUCCESS", media_type="text/plain")

    except Exception as e:
        detailed = f"Pipeline Error: {e}\n{traceback.format_exc()}"
        log.error(detailed)
        return Response(content=detailed, status_code=500, media_type="text/plain")


@app.get("/reply.wav")
async def get_reply_audio():
    if config.REPLY_WAV.exists():
        return FileResponse(config.REPLY_WAV, media_type="audio/wav")
    return Response(content="Error: reply.wav not found", status_code=404)


@app.get("/alerts")
async def list_alerts(unread_only: bool = False):
    alerts = database.get_alerts(unread_only=unread_only)
    return JSONResponse({"count": len(alerts), "alerts": alerts})


@app.post("/alerts/{alert_id}/read")
async def read_alert(alert_id: int):
    ok = database.mark_alert_read(alert_id)
    if not ok:
        return JSONResponse({"error": "Alert not found"}, status_code=404)
    return JSONResponse({"ok": True, "id": alert_id})


@app.get("/", response_class=HTMLResponse)
async def digital_twin_dashboard():
    """Parent digital twin: all chats, with problem chats marked in red + !"""
    chats = database.get_recent_chats(limit=30)
    alerts = database.get_alerts(unread_only=False, limit=10)
    unread = [a for a in alerts if not a.get("is_read")]
    flagged_count = database.count_flagged_chats()

    attention_html = ""
    if flagged_count:
        attention_html = f"""
        <div class="attention-banner">
            <span class="bang">!</span>
            Attention: {flagged_count} chat(s) need a parent look — click a red chat to open the full conversation
        </div>
        """

    if unread:
        alert_html = ""
        for a in unread:
            link_start = ""
            link_end = ""
            click_hint = ""
            if a.get("chat_id"):
                link_start = f'<a class="chat-link" href="/conversation/{a["chat_id"]}">'
                link_end = "</a>"
                click_hint = '<div class="click-hint">Click to open full conversation</div>'
            alert_html += f"""
            {link_start}
            <div class="alert-block severity-{_escape(a['severity'])}">
                <div><strong>! Alert ({_escape(a['severity'])})</strong> — {_escape(a['category'])}</div>
                <div>{_escape(a['summary'])}</div>
                <div class="advice">Tip: {_escape(a['parent_advice'])}</div>
                <div class="meta">Child said: "{_escape(a['child_message'])}"</div>
                {click_hint}
            </div>
            {link_end}
            """
    else:
        alert_html = "<p class='empty'>No unread safety alerts.</p>"

    if chats:
        chat_html = ""
        for chat in chats:
            flagged = bool(chat.get("is_flagged"))
            css = "chat-block flagged" if flagged else "chat-block"
            mark = '<span class="bang" title="Needs attention">!</span> ' if flagged else ""
            flag_meta = ""
            click_hint = ""
            open_tag = "<div>"
            close_tag = "</div>"
            if flagged:
                flag_meta = (
                    f"<div class='flag-reason'>"
                    f"{_escape(chat.get('alert_severity') or '')} · "
                    f"{_escape(chat.get('alert_category') or '')}: "
                    f"{_escape(chat.get('alert_summary') or '')}"
                    f"</div>"
                )
                click_hint = '<div class="click-hint">Click to see the full conversation</div>'
                open_tag = f'<a class="chat-link" href="/conversation/{chat["id"]}">'
                close_tag = "</a>"
            chat_html += f"""
            {open_tag}
            <div class="{css}">
                <div class="meta">{mark}mode: {_escape(chat.get('mode', 'free'))} · {_escape(chat.get('created_at', ''))}</div>
                <div class="user-msg"><strong>Child:</strong> {_escape(chat['child_message'])}</div>
                <div class="ai-msg"><strong>Robot:</strong> {_escape(chat['ai_reply'])}</div>
                {flag_meta}
                {click_hint}
            </div>
            {close_tag}
            """
    else:
        chat_html = "<p class='empty'>No conversations yet. Speak into the device!</p>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kids Robot — Parent Twin</title>
        <meta http-equiv="refresh" content="5">
        <style>{_page_styles()}</style>
    </head>
    <body>
        <div class="container">
            <h1>Kids Robot — Parent Twin</h1>
            <div class="status-bar">Live session · auto-refresh every 5s · mode: {_escape(features.get_current_mode())}</div>
            {attention_html}

            <h2>Safety alerts ({len(unread)} unread)</h2>
            {alert_html}

            <h2>Chat log (all saved · problems marked !)</h2>
            {chat_html}

            <div class="footer">
                SQLite file: data/parent_logs.db · tables: chats, alerts ·
                Click a red ! chat to open the full conversation
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/conversation/{chat_id}", response_class=HTMLResponse)
async def conversation_detail(chat_id: int):
    """Full conversation view for parents, opened from a problem chat."""
    focus_chat, messages = database.get_conversation_for_chat(chat_id)
    if not focus_chat:
        return HTMLResponse(
            "<h1>Conversation not found</h1><a href='/'>Back</a>",
            status_code=404,
        )

    session_id = focus_chat.get("session_id") or "unknown"
    alert_box = ""
    if focus_chat.get("is_flagged"):
        alert_box = f"""
        <div class="attention-banner">
            <span class="bang">!</span>
            Problem message highlighted below ·
            {_escape(focus_chat.get('alert_severity') or '')} /
            {_escape(focus_chat.get('alert_category') or '')}:
            {_escape(focus_chat.get('alert_summary') or '')}
        </div>
        """

    messages_html = ""
    for msg in messages:
        flagged = bool(msg.get("is_flagged"))
        is_focus = msg.get("id") == chat_id
        css = "chat-block"
        if flagged:
            css += " flagged"
        if is_focus:
            css += " highlight"
        mark = '<span class="bang">!</span> ' if flagged else ""
        messages_html += f"""
        <div class="{css}" id="msg-{msg['id']}">
            <div class="meta">{mark}#{msg['id']} · mode: {_escape(msg.get('mode', 'free'))} · {_escape(msg.get('created_at', ''))}</div>
            <div class="user-msg"><strong>Child:</strong> {_escape(msg['child_message'])}</div>
            <div class="ai-msg"><strong>Robot:</strong> {_escape(msg['ai_reply'])}</div>
        </div>
        """

    if not messages_html:
        messages_html = "<p class='empty'>No messages in this conversation.</p>"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Conversation — Parent Twin</title>
        <style>{_page_styles()}</style>
    </head>
    <body>
        <div class="container">
            <a class="back-link" href="/">&larr; Back to digital twin</a>
            <h1>Full conversation</h1>
            <div class="status-bar">Session: {_escape(str(session_id))} · {len(messages)} message(s)</div>
            {alert_box}
            <h2>Child ↔ Robot</h2>
            {messages_html}
            <div class="footer">Parents only — the AI does not re-read this conversation</div>
        </div>
        <script>
            const el = document.getElementById("msg-{chat_id}");
            if (el) el.scrollIntoView({{ behavior: "smooth", block: "center" }});
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host=config.HOST, port=config.PORT, reload=False)
