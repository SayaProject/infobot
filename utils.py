import html
from typing import Any, Optional, Tuple
from telegram import Message

# ─── SMALL-CAPS FONT ────────────────────────────────────────────────────────
_SC_TABLE = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
)

def sc(text: str) -> str:
    """Convert text to small-caps unicode."""
    return text.lower().translate(_SC_TABLE)


# ─── GENERIC HELPERS ────────────────────────────────────────────────────────
def safe_escape(text: Any) -> str:
    return "Null" if text is None else html.escape(str(text))


def get_media_id(message: Message) -> Tuple[Optional[str], Optional[str]]:
    """Return (type, file_id) for any media in message, else (None, None)."""
    if message.photo:
        return "photo", message.photo.file_id
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    return None, None


async def extract_user(message: Message) -> Optional[int]:
    """
    Resolve a user/chat ID from:
      1. text arg  (/cmd @username | /cmd 12345)
      2. reply-to message
      3. fallback → sender's own ID
    Returns None only when a username arg was given but lookup failed.
    """
    args = message.text.split() if message.text else []

    if len(args) > 1:
        target = args[1].strip()
        if target.lstrip("-").isdigit():
            return int(target)
        target = target.lstrip("@")
        try:
            chat = await message.get_bot().get_chat(target)
            return chat.id
        except Exception:
            return None

    if message.reply_to_message:
        r = message.reply_to_message
        if r.from_user:
            return r.from_user.id
        if r.sender_chat:
            return r.sender_chat.id

    # fallback — own ID
    if message.from_user:
        return message.from_user.id
    if message.sender_chat:
        return message.sender_chat.id

    return None
