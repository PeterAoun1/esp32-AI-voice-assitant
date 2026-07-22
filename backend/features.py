"""
Kid features:
1) Startup menu: story (fairy tale) / count to 20 / alphabet
2) Learning modes while chatting
3) Safety: bad-word filter + sensitive-topic check for parents
"""

import json
import logging
import re
import uuid
from typing import Optional

log = logging.getLogger("VoiceAssistant")

# --- Learning / activity modes ---
MODE_FREE = "free"
MODE_STORY = "story"
MODE_ALPHABET = "alphabet"
MODE_COUNT = "count"

MODE_PROMPTS = {
    MODE_FREE: (
        "You are a warm AI voice friend for young children. "
        "Speak calmly, simply, and briefly in English only. "
        "Have a normal, natural conversation. "
        "You can tell short fairy tales or help them learn if they ask. "
        "Do not push a menu every turn."
    ),
    MODE_STORY: (
        "You are a gentle storyteller for young children. "
        "Tell short fairy tales in English only, calmly and briefly for a small speaker. "
        "Keep each reply to a few sentences, then ask if they want the next part."
    ),
    MODE_ALPHABET: (
        "You are a cheerful alphabet teacher for young children. "
        "Speak English only. Keep answers very short. Teach letters A to Z a few at a time "
        "(3 to 5 letters). Say each letter clearly, give one simple word example, then ask "
        "the child to repeat. If they finish Z, celebrate and offer counting to 20 or a fairy tale."
    ),
    MODE_COUNT: (
        "You are a cheerful counting teacher for young children. "
        "Speak English only. Keep answers very short. Help count from 1 to 20, about 5 numbers "
        "per turn, then ask them to say the next number. If they reach 20, celebrate and offer "
        "the alphabet or a fairy tale."
    ),
}

# Natural greeting when the robot starts (not a menu dump)
WELCOME_TEXT = (
    "Hi! I am happy to talk with you. How are you today?"
)

# Soft offer only if the child's first message did not pick an activity
MENU_OFFER_AFTER_FIRST_MESSAGE = (
    "Would you like to hear a story, learn how to count to twenty, "
    "or learn the alphabet? Just tell me what you prefer!"
)

# Session flags
_current_mode = MODE_FREE
_awaiting_menu_choice = False
_child_turn_count = 0
_current_session_id: Optional[str] = None
_append_activity_offer = False


def get_current_mode() -> str:
    return _current_mode


def get_current_session_id() -> str:
    """Return the active conversation session id (create one if needed)."""
    global _current_session_id
    if not _current_session_id:
        _current_session_id = uuid.uuid4().hex[:12]
        log.info(f"Started conversation session: {_current_session_id}")
    return _current_session_id


def is_awaiting_menu_choice() -> bool:
    return _awaiting_menu_choice


def set_current_mode(mode: str) -> None:
    global _current_mode
    if mode in MODE_PROMPTS:
        _current_mode = mode
        log.info(f"Learning mode set to: {mode}")


def start_welcome_menu() -> str:
    """Start a normal session with a friendly greeting (not a forced menu)."""
    global _awaiting_menu_choice, _current_mode, _child_turn_count
    global _current_session_id, _append_activity_offer
    _awaiting_menu_choice = False
    _append_activity_offer = False
    _current_mode = MODE_FREE
    _child_turn_count = 0
    _current_session_id = uuid.uuid4().hex[:12]
    log.info(f"Session started with normal greeting — session={_current_session_id}")
    return WELCOME_TEXT


def consume_activity_offer() -> Optional[str]:
    """
    If the first child message had no activity choice,
    return a short offer to append after the normal AI reply.
    """
    global _append_activity_offer, _awaiting_menu_choice
    if not _append_activity_offer:
        return None
    _append_activity_offer = False
    _awaiting_menu_choice = True
    return MENU_OFFER_AFTER_FIRST_MESSAGE


def system_prompt_for_mode(mode: Optional[str] = None) -> str:
    return MODE_PROMPTS.get(mode or _current_mode, MODE_PROMPTS[MODE_FREE])


def _pick_mode_from_keywords(text: str) -> Optional[str]:
    """Return a mode if the text clearly asks for one activity."""
    t = (text or "").lower()

    story_words = ("story", "stories", "fairy", "fairy tale", "fairytale")
    if any(word in t for word in story_words):
        return MODE_STORY

    alphabet_words = ("alphabet", "abc", "a b c", "letters", "letter")
    if any(word in t for word in alphabet_words):
        return MODE_ALPHABET

    count_words = (
        "count to 20", "count to twenty", "counting", "count with me",
        "numbers to 20", "count",
    )
    if any(word in t for word in count_words) or ("count" in t and "20" in t):
        return MODE_COUNT

    return None


def detect_mode_from_text(text: str) -> str:
    """Detect if the child asked to switch mode (keyword matching, no AI cost)."""
    global _current_mode, _awaiting_menu_choice

    picked = _pick_mode_from_keywords(text)
    if picked:
        _current_mode = picked
        _awaiting_menu_choice = False
        return _current_mode

    t = (text or "").lower().strip()
    if any(word in t for word in ("stop", "normal chat", "just talk")):
        _current_mode = MODE_FREE
        _awaiting_menu_choice = False
        return MODE_FREE

    return _current_mode


def reply_after_menu_choice(mode: str) -> str:
    """First spoken reply after the child picks an activity (no LLM cost)."""
    if mode == MODE_STORY:
        return (
            "Great! Here is a little fairy tale. "
            "Once upon a time, a kind princess and a friendly dragon guarded "
            "a treasure of magic cookies. Do you want the next part?"
        )
    if mode == MODE_COUNT:
        return (
            "Perfect! Let's count together. One, two, three, four, five. "
            "Your turn! What number comes after five?"
        )
    if mode == MODE_ALPHABET:
        return (
            "Awesome! Let's start the alphabet. A, B, C. "
            "A for apple, B for ball, C for cat. Can you say A, B, C?"
        )
    return "Okay! Tell me if you want a story, counting, or the alphabet."


def handle_child_turn(user_text: str) -> tuple[str, str, bool]:
    """
    Decide mode + whether we should use a fixed starter reply
    instead of calling the LLM.

    Rules:
    - Normal conversation by default (real AI / Groq)
    - If child clearly picks story / count / alphabet -> start that activity
    - After the FIRST child message with no activity choice -> AI answers normally,
      then we gently append an offer for story / count / alphabet

    Returns: (mode, optional_fixed_reply, used_fixed_reply)
    """
    global _awaiting_menu_choice, _current_mode, _child_turn_count, _append_activity_offer

    _child_turn_count += 1
    picked = _pick_mode_from_keywords(user_text)

    if picked:
        switching = _awaiting_menu_choice or (_current_mode != picked)
        _current_mode = picked
        _awaiting_menu_choice = False
        _append_activity_offer = False
        if switching:
            return picked, reply_after_menu_choice(picked), True
        return picked, "", False

    # First child sentence with no clear activity:
    # use the real AI reply, then gently offer the 3 options
    if _child_turn_count == 1:
        _append_activity_offer = True
        _current_mode = MODE_FREE
        return MODE_FREE, "", False

    # They were offered choices earlier but talked about something else -> normal chat
    _awaiting_menu_choice = False
    mode = detect_mode_from_text(user_text)
    return mode, "", False


# --- Safety / parent alerts ---

BAD_WORDS = {
    "fuck", "shit", "bitch", "asshole", "bastard", "dick", "pussy", "cunt",
    "slut", "whore", "nigger", "faggot",
}

SENSITIVE_CATEGORIES = (
    "bullying",
    "sadness_or_depression",
    "fear_or_anxiety",
    "violence",
    "self_harm",
    "abuse_or_neglect",
    "inappropriate_content",
    "family_conflict",
    "loneliness",
    "other_concerning",
)


def find_bad_words(text: str) -> list[str]:
    """Fast local check — no API credits."""
    words = re.findall(r"[a-zA-Z']+", (text or "").lower())
    return sorted({w for w in words if w in BAD_WORDS})


def analyze_sensitive_topic(ai_client, model: str, child_text: str) -> dict:
    """Ask Groq if the child's message needs parent attention."""
    empty = {
        "is_sensitive": False,
        "category": "none",
        "severity": "none",
        "summary": "",
        "parent_advice": "",
    }
    if not child_text or not child_text.strip():
        return empty

    bad = find_bad_words(child_text)
    if bad:
        return {
            "is_sensitive": True,
            "category": "inappropriate_content",
            "severity": "medium",
            "summary": f"Child used inappropriate language: {', '.join(bad)}",
            "parent_advice": "Gently explain which words are not okay and why.",
        }

    categories = ", ".join(SENSITIVE_CATEGORIES)
    system_prompt = (
        "You are a child-safety analyst for a kids companion robot. "
        "Flag only real distress, harm, bullying, abuse hints, or unsafe topics. "
        "Normal play, jokes, and story requests are NOT sensitive. "
        f"If sensitive, choose one category from: {categories}. "
        "Severity must be low, medium, or high. "
        "Respond ONLY with JSON keys: is_sensitive, category, severity, summary, parent_advice."
    )

    try:
        response = ai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": child_text},
            ],
            max_tokens=200,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

        result = json.loads(raw)
        if not result.get("is_sensitive"):
            return empty

        category = result.get("category", "other_concerning")
        if category not in SENSITIVE_CATEGORIES:
            category = "other_concerning"
        severity = result.get("severity", "medium")
        if severity not in ("low", "medium", "high"):
            severity = "medium"

        return {
            "is_sensitive": True,
            "category": category,
            "severity": severity,
            "summary": str(result.get("summary", "Sensitive topic detected.")).strip(),
            "parent_advice": str(result.get("parent_advice", "Check in gently with your child.")).strip(),
        }
    except Exception as e:
        log.error(f"Sensitive topic analysis failed: {e}")
        return empty
