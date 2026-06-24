import asyncio
import logging
from aiohttp import web
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from client import pbot
from info import (
    chat_info_handler,
    user_info_handler,
    id_handler,
    members_handler,
)

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── /start ──────────────────────────────────────────────────────────────────
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "<b>ɪɴꜰᴏ ʙᴏᴛ — ʙʏ SayaProject</b>\n"
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        "<b>/user</b> <code>@username</code> — ᴜꜱᴇʀ ɪɴꜰᴏ\n"
        "<b>/chat</b> <code>-100xxx</code> — ᴄʜᴀᴛ/ᴄʜᴀɴɴᴇʟ ɪɴꜰᴏ\n"
        "<b>/id</b> — ɢᴇᴛ ɪᴅꜱ (ᴜꜱᴇʀ, ᴄʜᴀᴛ, ᴍꜱɢ, ᴍᴇᴅɪᴀ)\n"
        "<b>/members</b> — ʟɪꜱᴛ ᴀʟʟ ᴜꜱᴇʀ ɪᴅꜱ ɪɴ ɢʀᴏᴜᴘ/ᴄʜᴀɴɴᴇʟ\n"
        "<b>━━━━━━━━━━━━━━━━</b>\n"
        "ᴛɪᴘꜱ: ʀᴇᴘʟʏ ᴛᴏ ᴀɴʏ ᴍᴇꜱꜱᴀɢᴇ ᴡɪᴛʜ <b>/id</b> ᴏʀ <b>/user</b>",
        parse_mode=constants.ParseMode.HTML,
    )


# ─── HEALTH SERVER ────────────────────────────────────────────────────────────
async def run_health_server():
    handler = lambda r: web.Response(text="OK")
    candidates = [config.PORT, config.PORT + 1, 8080, 8443, 5000]
    for port in candidates:
        try:
            app = web.Application()
            app.router.add_get("/", handler)
            app.router.add_get("/health", handler)
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", port).start()
            logger.info("Health server: port %d", port)
            return
        except OSError:
            continue
    logger.warning("No port available for health server")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    # start Pyrogram
    await pbot.start()
    logger.info("Pyrogram OK")

    # build PTB app
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",             start_handler))
    app.add_handler(CommandHandler(["user", "info"],    user_info_handler))
    app.add_handler(CommandHandler(["chat", "ginfo"],   chat_info_handler))
    app.add_handler(CommandHandler("id",                id_handler))
    app.add_handler(CommandHandler("members",           members_handler))

    await run_health_server()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot live — polling")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await pbot.stop()


if __name__ == "__main__":
    asyncio.run(main())
