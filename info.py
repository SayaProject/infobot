import io
import html
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, Any
from cachetools import TTLCache

from telegram import constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from client import pbot
from utils import sc, safe_escape, get_media_id, extract_user
import config

logger = logging.getLogger(__name__)

# ─── DC MAP ─────────────────────────────────────────────────────────────────
DC_LOCATIONS = {
    1: "MIA, Miami, FL, USA",
    2: "AMS, Amsterdam, NL",
    3: "MIA, Miami, FL, USA",
    4: "AMS, Amsterdam, NL",
    5: "SIN, Singapore, SG",
}

# ─── STATUS CACHE ────────────────────────────────────────────────────────────
_status_cache: TTLCache = TTLCache(maxsize=512, ttl=30)


# ─── HELPERS ─────────────────────────────────────────────────────────────────
def format_chat_id(raw: str) -> str:
    if raw.startswith("https://t.me/"):
        return "@" + raw.split("/")[-1]
    return raw


def calculate_account_age(creation_date: datetime) -> str:
    total_days = (datetime.now() - creation_date).days
    years = total_days // 365
    months = (total_days % 365) // 30
    days = (total_days % 365) % 30
    return f"{years} years, {months} months, {days} days"


def estimate_account_creation_date(user_id: int) -> datetime:
    refs = [
        (100_000_000,   datetime(2013, 8, 1)),
        (1_273_841_502, datetime(2020, 8, 13)),
        (1_500_000_000, datetime(2021, 5, 1)),
        (2_000_000_000, datetime(2022, 12, 1)),
    ]
    base_id, base_date = min(refs, key=lambda x: abs(x[0] - user_id))
    return base_date + timedelta(days=(user_id - base_id) / 20_000_000)


async def get_photo_bytes(bot, photo_id: str) -> Optional[bytes]:
    # 1) try Pyrogram download (best quality)
    try:
        media = await pbot.download_media(photo_id, in_memory=True)
        if media:
            return media.getvalue() if hasattr(media, "getvalue") else bytes(media)
    except Exception as e:
        logger.debug("pyro dl failed: %s", e)

    # 2) try PTB file URL
    try:
        f = await bot.get_file(photo_id)
        if f.file_path:
            if f.file_path.startswith("/"):
                with open(f.file_path, "rb") as fp:
                    return fp.read()
            if f.file_path.startswith("http"):
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as s:
                    async with s.get(f.file_path) as r:
                        if r.status == 200:
                            return await r.read()
        return bytes(await f.download_as_bytearray())
    except Exception as e:
        logger.warning("ptb dl failed: %s", e)

    return None


async def get_status_text(user_id: int) -> str:
    if user_id == config.OWNER_ID:
        return "👑 Owner"
    return ""


def build_chat_info_text(chat) -> str:
    ctype_map = {
        constants.ChatType.CHANNEL:    "Channel",
        constants.ChatType.GROUP:      "Group",
        constants.ChatType.SUPERGROUP: "Supergroup",
    }
    chat_type   = ctype_map.get(chat.type, "Chat")
    title       = getattr(chat, "title", "Unknown")
    username    = getattr(chat, "username", None)
    member_count = getattr(chat, "member_count", None)
    description = getattr(chat, "description", None)

    t = (
        f"<b>ꜱʜᴏᴡɪɴɢ {chat_type}'ꜱ ᴘʀᴏꜰɪʟᴇ ɪɴꜰᴏ</b>\n"
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        f"<b>ᴄʜᴀᴛ ᴛɪᴛʟᴇ:</b> <b>{safe_escape(title)}</b>\n"
    )
    if username:
        t += f"<b>ᴜꜱᴇʀɴᴀᴍᴇ:</b> @{username}\n"
    t += f"<b>ᴄʜᴀᴛ ɪᴅ:</b> <code>{chat.id}</code>\n"
    t += f"<b>ᴄʜᴀᴛ ᴛʏᴘᴇ:</b> <b>{chat_type}</b>\n"
    if member_count:
        t += f"<b>ᴛᴏᴛᴀʟ ᴍᴇᴍʙᴇʀꜱ:</b> <b>{member_count}</b>\n"
    if description:
        t += f"<b>ᴅᴇꜱᴄʀɪᴘᴛɪᴏɴ:</b> <code>{safe_escape(description)}</code>\n"
    if username:
        t += f"<b>ᴘᴇʀᴍᴀɴᴇɴᴛ ʟɪɴᴋ:</b> <a href='https://t.me/{username}'>Click Here</a>\n"
    t += (
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        "<b>ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜꜱɪɴɢ ᴏᴜʀ ᴛᴏᴏʟ</b>"
    )
    return t


# ─── HANDLERS ────────────────────────────────────────────────────────────────

async def chat_info_handler(update, context):
    """
    /chat -100xxxx  or  /ginfo @username
    Works from DM (requires arg) or group (defaults to current chat).
    """
    bot = context.bot
    m   = update.effective_message
    cur = update.effective_chat

    if cur.type == constants.ChatType.PRIVATE and len(m.text.split()) < 2:
        await m.reply_text(
            "<b>ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɴᴇᴇᴅꜱ ᴀ ᴄʜᴀᴛ ɪᴅ ᴏʀ ᴜꜱᴇʀɴᴀᴍᴇ.</b>\n"
            "<b>ᴇxᴀᴍᴘʟᴇ:</b> <code>/chat -1001234567890</code>\n"
            "<b>ᴏʀ:</b> <code>/chat @channelusername</code>",
            parse_mode=constants.ParseMode.HTML,
        )
        return

    msg_task = asyncio.create_task(
        m.reply_text("<code>ᴘʀᴏᴄᴇꜱꜱɪɴɢ ᴄʜᴀᴛ ɪɴꜰᴏ...</code>",
                     parse_mode=constants.ParseMode.HTML)
    )

    # determine target chat_id
    chat_id = cur.id
    if len(m.text.split()) > 1:
        raw = m.text.split()[1].strip()
        chat_id = format_chat_id(raw)
        if not (str(chat_id).startswith("@") or str(chat_id).startswith("-100")):
            msg = await msg_task
            await msg.edit_text(
                "<b>ɢɪᴠᴇ ᴀ ᴠᴀʟɪᴅ ᴄʜᴀᴛ ᴜꜱᴇʀɴᴀᴍᴇ ᴏʀ ɪᴅ.</b>",
                parse_mode=constants.ParseMode.HTML,
            )
            return

    msg = await msg_task
    try:
        chat = await bot.get_chat(chat_id)
        text = build_chat_info_text(chat)

        if chat.photo:
            photo_bytes = await get_photo_bytes(bot, chat.photo.big_file_id)
            if photo_bytes:
                await m.reply_photo(
                    photo=photo_bytes,
                    caption=text,
                    parse_mode=constants.ParseMode.HTML,
                )
                await msg.delete()
                return

        await msg.edit_text(text=text, parse_mode=constants.ParseMode.HTML)

    except Exception as e:
        await msg.edit_text(
            f"<b>ᴇʀʀᴏʀ:</b> {html.escape(str(e))}",
            parse_mode=constants.ParseMode.HTML,
        )


async def user_info_handler(update, context):
    """
    /user @username  |  /info <user_id>  |  reply + /info
    """
    message = update.effective_message
    bot     = context.bot
    chat    = update.effective_chat

    user_id = await extract_user(message)
    if not user_id:
        await message.reply_text(
            "ᴄᴀɴ'ᴛ ꜰɪɴᴅ ᴜꜱᴇʀ. ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇꜱꜱᴀɢᴇ ᴏʀ ɢɪᴠᴇ ᴜꜱᴇʀɴᴀᴍᴇ/ɪᴅ."
        )
        return

    # prefer forwarded origin
    if (
        message.reply_to_message
        and message.reply_to_message.forward_origin
        and getattr(message.reply_to_message.forward_origin, "sender_user", None)
    ):
        user_id = message.reply_to_message.forward_origin.sender_user.id

    msg_task = asyncio.create_task(
        message.reply_text(
            "<code>ᴘʀᴏᴄᴇꜱꜱɪɴɢ ᴜꜱᴇʀ ɪɴꜰᴏ...</code>",
            parse_mode=constants.ParseMode.HTML,
        )
    )

    try:
        user_task = asyncio.create_task(bot.get_chat(user_id))
        msg, user = await asyncio.gather(msg_task, user_task)

        pyro_user    = await pbot.get_users(user_id)
        dc_id        = getattr(pyro_user, "dc_id", None)
        is_premium   = getattr(pyro_user, "is_premium", False)
        is_bot_acc   = getattr(pyro_user, "is_bot", False)
        is_restricted = getattr(pyro_user, "is_restricted", False)

    except Exception as e:
        msg = await msg_task
        await msg.edit_text(
            f"<b>ᴇʀʀᴏʀ:</b> {html.escape(str(e))}",
            parse_mode=constants.ParseMode.HTML,
        )
        return

    dc_location  = DC_LOCATIONS.get(dc_id, "Unknown")
    premium_txt  = "Yes" if is_premium else "No"
    created_dt   = estimate_account_creation_date(user.id)
    created_str  = created_dt.strftime("%B %d, %Y")
    age_str      = calculate_account_age(created_dt)

    first = getattr(user, "first_name", "Unknown") or "Unknown"
    last  = getattr(user, "last_name", "") or ""
    full  = f"{first} {last}".strip()
    uname = getattr(user, "username", None)

    in_group = chat.type in (constants.ChatType.GROUP, constants.ChatType.SUPERGROUP)
    ptype    = "ʙᴏᴛ'ꜱ ᴘʀᴏꜰɪʟᴇ ɪɴꜰᴏ" if is_bot_acc else "ᴜꜱᴇʀ'ꜱ ᴘʀᴏꜰɪʟᴇ ɪɴꜰᴏ"

    t = (
        f"<b>ꜱʜᴏᴡɪɴɢ {ptype}</b>\n"
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        f"<b>ꜰᴜʟʟ ɴᴀᴍᴇ:</b> <b>{safe_escape(full)}</b>\n"
    )
    if uname:
        t += f"<b>ᴜꜱᴇʀɴᴀᴍᴇ:</b> @{uname}\n"
    t += f"<b>ᴜꜱᴇʀ ɪᴅ:</b> <code>{user.id}</code>\n"
    if in_group:
        t += f"<b>ᴄʜᴀᴛ ɪᴅ:</b> <code>{chat.id}</code>\n"
    if not is_bot_acc:
        t += f"<b>ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀ:</b> <b>{premium_txt}</b>\n"
    t += f"<b>ᴅᴀᴛᴀ ᴄᴇɴᴛᴇʀ:</b> <b>{dc_location}</b>\n"
    if not is_bot_acc:
        t += (
            f"<b>ᴄʀᴇᴀᴛᴇᴅ ᴏɴ:</b> <b>{created_str}</b>\n"
            f"<b>ᴀᴄᴄᴏᴜɴᴛ ᴀɢᴇ:</b> <b>{age_str}</b>\n"
        )
    t += f"<b>ᴀᴄᴄᴏᴜɴᴛ ꜰʀᴏᴢᴇɴ:</b> <b>{'Yes' if is_restricted else 'No'}</b>\n"

    # status (owner / group role)
    status = await get_status_text(user.id)
    if in_group:
        try:
            member = await bot.get_chat_member(chat.id, user.id)
            if member.status == constants.ChatMemberStatus.OWNER:
                status = f"{status} | 👑 Group Owner" if status else "👑 Group Owner"
            elif member.status == constants.ChatMemberStatus.ADMINISTRATOR:
                status = f"{status} | ⚙️ Admin" if status else "⚙️ Admin"
        except Exception:
            pass
    if status:
        t += f"<b>ꜱᴛᴀᴛᴜꜱ:</b> {status}\n"

    # last seen (from Pyrogram)
    try:
        s = str(getattr(await pbot.get_users(user_id), "status", ""))
        seen = (
            "Online"    if "ONLINE"     in s else
            "Recently"  if "RECENTLY"   in s else
            "Last Week"  if "LAST_WEEK"  in s else
            "Last Month" if "LAST_MONTH" in s else
            "Long Ago"  if "LONG_AGO"   in s else "Unknown"
        )
        t += f"<b>ʟᴀꜱᴛ ꜱᴇᴇɴ:</b> <b>{seen}</b>\n"
    except Exception:
        t += "<b>ʟᴀꜱᴛ ꜱᴇᴇɴ:</b> <b>Unknown</b>\n"

    bio = getattr(user, "bio", None)
    if bio:
        t += f"<b>ʙɪᴏ:</b> <code>{safe_escape(bio)}</code>\n"

    t += (
        f"<b>ᴘᴇʀᴍᴀɴᴇɴᴛ ʟɪɴᴋ:</b> <a href='tg://user?id={user.id}'>Click Here</a>\n"
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        "<b>ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜꜱɪɴɢ ᴏᴜʀ ᴛᴏᴏʟ</b>"
    )

    keyboard = None
    try:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"💬 {full}", url=f"tg://user?id={user.id}")]]
        )
    except Exception:
        pass

    # photo reply
    if user.photo:
        photo_bytes = await get_photo_bytes(bot, user.photo.big_file_id)
        if photo_bytes:
            for kb in [keyboard, None]:
                try:
                    await message.reply_photo(
                        photo=photo_bytes,
                        caption=t,
                        parse_mode=constants.ParseMode.HTML,
                        reply_markup=kb,
                    )
                    await msg.delete()
                    return
                except BadRequest as e:
                    if "Button_user_privacy_restricted" in str(e) and kb:
                        continue
                    break

    # text reply fallback
    try:
        await msg.edit_text(t, parse_mode=constants.ParseMode.HTML, reply_markup=keyboard)
    except BadRequest as e:
        if "Button_user_privacy_restricted" in str(e):
            await msg.edit_text(t, parse_mode=constants.ParseMode.HTML)


async def id_handler(update, context):
    """
    /id            — your ID + chat ID + msg ID
    /id @user      — look up user ID
    reply + /id    — reply info + media file_id
    """
    bot     = context.bot
    message = update.effective_message
    reply   = message.reply_to_message

    if len(message.text.split()) > 1:
        try:
            uid = await extract_user(message)
            if not uid:
                await message.reply_text("ᴄᴏᴜʟᴅɴ'ᴛ ꜰɪɴᴅ ᴜꜱᴇʀ...")
                return
            user = await bot.get_chat(uid)
            txt = (
                f"👤 ᴜꜱᴇʀ: `{user.first_name}`\n"
                f"🆔 ᴜꜱᴇʀ ɪᴅ: `{user.id}`"
            )
            try:
                kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("💬 Mention", url=f"tg://user?id={user.id}")]]
                )
                await message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN,
                                         reply_markup=kb)
            except BadRequest as e:
                if "Button_user_privacy_restricted" in str(e):
                    await message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)
                else:
                    raise
        except Exception as e:
            await message.reply_text(f"ᴇʀʀᴏʀ: `{str(e)}`",
                                     parse_mode=constants.ParseMode.MARKDOWN)
        return

    sender_id = (
        message.sender_chat.id if message.sender_chat else message.from_user.id
    )
    txt = (
        f"👤 ʏᴏᴜʀ ᴛɢ ɪᴅ: `{sender_id}`\n"
        f"💬 ᴄʜᴀᴛ ɪᴅ: `{message.chat.id}`\n"
        f"📩 ᴍꜱɢ ɪᴅ: `{message.message_id}`"
    )

    if reply:
        reply_id = reply.sender_chat.id if reply.sender_chat else reply.from_user.id
        txt += (
            f"\n↩️ ʀᴇᴘʟɪᴇᴅ ᴛɢ ɪᴅ: `{reply_id}`"
            f"\n📩 ʀᴇᴘʟɪᴇᴅ ᴍꜱɢ ɪᴅ: `{reply.message_id}`"
        )
        if reply.forward_origin:
            fwd = reply.forward_origin
            if getattr(fwd, "sender_user", None):
                txt += f"\n↗️ ꜰᴏʀᴡᴀʀᴅ ᴜꜱᴇʀ ɪᴅ: `{fwd.sender_user.id}`"
            elif getattr(fwd, "chat", None):
                txt += f"\n↗️ ꜰᴏʀᴡᴀʀᴅ ᴄʜᴀᴛ ɪᴅ: `{fwd.chat.id}`"
        mtype, mid = get_media_id(reply)
        if mtype and mid:
            txt += f"\n📎 {mtype.capitalize()} ɪᴅ: `{mid}`"

    await message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN)


async def members_handler(update, context):
    """
    /members  — dump all user IDs of the current group or channel.
    Bot must be admin. Sends inline for ≤30 members, else .txt file.
    """
    m    = update.effective_message
    chat = update.effective_chat

    if chat.type == constants.ChatType.PRIVATE:
        await m.reply_text(
            "<b>ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ɪɴꜱɪᴅᴇ ᴀ ɢʀᴏᴜᴘ ᴏʀ ᴄʜᴀɴɴᴇʟ.</b>",
            parse_mode=constants.ParseMode.HTML,
        )
        return

    msg = await m.reply_text(
        "<code>ꜰᴇᴛᴄʜɪɴɢ ᴍᴇᴍʙᴇʀꜱ...</code>",
        parse_mode=constants.ParseMode.HTML,
    )

    try:
        rows   = []
        count  = 0
        bots   = 0

        async for member in pbot.get_chat_members(chat.id):
            u     = member.user
            fname = (u.first_name or "").strip()
            lname = (u.last_name  or "").strip()
            name  = f"{fname} {lname}".strip() or "Unknown"
            uname = f"@{u.username}" if u.username else "-"
            tag   = " [BOT]" if u.is_bot else ""
            if u.is_bot:
                bots += 1
            rows.append(f"{u.id:<15} | {name}{tag} | {uname}")
            count += 1

        if count == 0:
            await msg.edit_text(
                "<b>ɴᴏ ᴍᴇᴍʙᴇʀꜱ ꜰᴏᴜɴᴅ.</b>",
                parse_mode=constants.ParseMode.HTML,
            )
            return

        sep    = "─" * 55
        header = (
            f"ᴄʜᴀᴛ    : {chat.title}\n"
            f"ᴄʜᴀᴛ ɪᴅ : {chat.id}\n"
            f"ᴛᴏᴛᴀʟ   : {count}  (ʙᴏᴛꜱ: {bots}  ᴜꜱᴇʀꜱ: {count - bots})\n"
            f"{sep}\n"
            f"{'ɪᴅ':<15} | ɴᴀᴍᴇ | ᴜꜱᴇʀɴᴀᴍᴇ\n"
            f"{sep}\n"
        )
        content = header + "\n".join(rows)

        if count <= 30:
            await msg.edit_text(
                f"<pre>{html.escape(content)}</pre>",
                parse_mode=constants.ParseMode.HTML,
            )
        else:
            buf      = io.BytesIO(content.encode("utf-8"))
            buf.name = f"members_{abs(chat.id)}.txt"
            await m.reply_document(
                document=buf,
                caption=(
                    f"<b>ᴄʜᴀᴛ:</b> {safe_escape(chat.title)}\n"
                    f"<b>ᴛᴏᴛᴀʟ:</b> {count} ᴍᴇᴍʙᴇʀꜱ "
                    f"(ᴜꜱᴇʀꜱ: {count - bots}  ʙᴏᴛꜱ: {bots})"
                ),
                parse_mode=constants.ParseMode.HTML,
            )
            await msg.delete()

    except Exception as e:
        await msg.edit_text(
            f"<b>ᴇʀʀᴏʀ:</b> {html.escape(str(e))}\n\n"
            "<i>Make sure the bot is an admin in this chat.</i>",
            parse_mode=constants.ParseMode.HTML,
        )
