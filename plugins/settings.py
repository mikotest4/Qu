from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters
)
from helper_func.settings_manager import SettingsManager

# Conversation states
RESOLUTION, FPS, CODEC, CRF, PRESET = range(5)

# Option definitions
RESOLUTIONS = [
    ('8K', '7680:4320'),
    ('4K', '3840:2160'),
    ('1440p', '2560:1440'),
    ('1080p', '1920:1080'),
    ('720p', '1280:720'),
    ('480p', '854:480'),
    ('360p', '640:360'),
    ('240p', '426:240'),
    ('144p', '256:144'),
    ('original', 'original'),
]
FPS_OPTIONS = [
    ('60 FPS', '60'),
    ('50 FPS', '50'),
    ('30 FPS', '30'),
    ('25 FPS', '25'),
    ('24 FPS', '24'),
    ('original', 'original'),
]
CODECS = [
    ('H.264', 'libx264'),
    ('H.265', 'libx265'),
    ('VP9',   'libvpx-vp9'),
    ('AV1',   'libaom-av1'),
]
PRESETS = [
    ('ultrafast','ultrafast'),
    ('superfast','superfast'),
    ('veryfast','veryfast'),
    ('faster','faster'),
    ('fast','fast'),
    ('medium','medium'),
    ('slow','slow'),
    ('slower','slower'),
    ('veryslow','veryslow'),
]

async def start_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(n, callback_data=v)] for n,v in RESOLUTIONS]
    await update.message.reply_text("Choose your desired video resolution:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))
    return RESOLUTION

async def pick_resolution(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user
    sel = update.callback_query.data
    SettingsManager.set(user.id, 'resolution', sel)
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton(n, callback_data=v)] for n,v in FPS_OPTIONS]
    await update.callback_query.edit_message_text("Now pick your target FPS:",
                                                 reply_markup=InlineKeyboardMarkup(keyboard))
    return FPS

async def pick_fps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user
    sel = update.callback_query.data
    SettingsManager.set(user.id, 'fps', sel)
    await update.callback_query.answer()
    keyboard = [[InlineKeyboardButton(n, callback_data=v)] for n,v in CODECS]
    await update.callback_query.edit_message_text("Choose your video codec:",
                                                 reply_markup=InlineKeyboardMarkup(keyboard))
    return CODEC

async def pick_codec(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user
    sel = update.callback_query.data
    SettingsManager.set(user.id, 'codec', sel)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send me a CRF value (0–51):")
    return CRF

async def pick_crf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    txt = update.message.text.strip()
    if not txt.isdigit() or not (0 <= int(txt) <= 51):
        return await update.message.reply_text("❌ Enter a number between 0 and 51.")
    SettingsManager.set(user.id, 'crf', txt)
    keyboard = [[InlineKeyboardButton(n, callback_data=v)] for n,v in PRESETS]
    await update.message.reply_text("Finally, choose your encoding preset:",
                                   reply_markup=InlineKeyboardMarkup(keyboard))
    return PRESET

async def pick_preset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user
    sel = update.callback_query.data
    SettingsManager.set(user.id, 'preset', sel)
    await update.callback_query.answer()
    cfg = SettingsManager.get(user.id)
    summary = (
        f"✅ Settings saved!\n"
        f"• Resolution: {cfg['resolution']}\n"
        f"• FPS: {cfg['fps']}\n"
        f"• Codec: {cfg['codec']}\n"
        f"• CRF: {cfg['crf']}\n"
        f"• Preset: {cfg['preset']}\n"
    )
    await update.callback_query.edit_message_text(summary)
    return ConversationHandler.END

async def cancel_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Settings setup canceled.")
    return ConversationHandler.END

def settings_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('settings', start_settings)],
        states={
            RESOLUTION: [CallbackQueryHandler(pick_resolution)],
            FPS:        [CallbackQueryHandler(pick_fps)],
            CODEC:      [CallbackQueryHandler(pick_codec)],
            CRF:        [MessageHandler(filters.TEXT & ~filters.COMMAND, pick_crf)],
            PRESET:     [CallbackQueryHandler(pick_preset)],
        },
        fallbacks=[CommandHandler('cancel', cancel_settings)],
        per_user=True,
    )
