# plugins/settings.py

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper_func.settings_manager import SettingsManager

# in‑memory state for who’s mid‑flow
_PENDING = {}

# Your option lists
RESOLUTIONS = [
    ('8K','7680:4320'),('4K','3840:2160'),
    ('1440p','2560:1440'),('1080p','1920:1080'),
    ('720p','1280:720'),('480p','854:480'),
    ('360p','640:360'),('240p','426:240'),
    ('144p','256:144'),('original','original'),
]
FPS_OPTIONS = [
    ('60 FPS','60'),('50 FPS','50'),
    ('30 FPS','30'),('25 FPS','25'),
    ('24 FPS','24'),('original','original'),
]
CODECS = [
    ('H.264','libx264'),('H.265','libx265'),
    ('VP9','libvpx-vp9'),('AV1','libaom-av1'),
]
PRESETS = [
    ('ultrafast','ultrafast'),('superfast','superfast'),
    ('veryfast','veryfast'),('faster','faster'),
    ('fast','fast'),('medium','medium'),
    ('slow','slow'),('slower','slower'),
    ('veryslow','veryslow'),
]

def _keyboard(options: list, tag: str) -> InlineKeyboardMarkup:
    """
    Build a one‑button‑per‑row keyboard where callback_data = "tag*value"
    """
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(n, callback_data=f"{tag}*{v}")]
         for n, v in options]
    )

@Client.on_message(filters.command("settings") & filters.private)
async def start_settings(client: Client, message):
    """Entry point: show resolution choices."""
    uid = message.from_user.id
    _PENDING[uid] = 'res'
    await message.reply(
        "🔧 **Settings:**\nChoose your target resolution:",
        reply_markup=_keyboard(RESOLUTIONS, 'res'),
        parse_mode="markdown"
    )

@Client.on_callback_query()
async def handle_settings_cb(client: Client, cq):
    """Handle each button press in the settings flow."""
    uid = cq.from_user.id
    stage = _PENDING.get(uid)
    if not stage:
        return  # not in a settings flow

    action, val = cq.data.split('*', 1)
    await cq.answer()  # remove the “loading” circle

    if action == 'res':
        SettingsManager.set(uid, 'resolution', val)
        _PENDING[uid] = 'fps'
        await cq.edit_message_text(
            "Choose your target frame rate:",
            reply_markup=_keyboard(FPS_OPTIONS, 'fps')
        )

    elif action == 'fps':
        SettingsManager.set(uid, 'fps', val)
        _PENDING[uid] = 'codec'
        await cq.edit_message_text(
            "Choose your video codec:",
            reply_markup=_keyboard(CODECS, 'codec')
        )

    elif action == 'codec':
        SettingsManager.set(uid, 'codec', val)
        _PENDING[uid] = 'crf'
        await cq.edit_message_text("Now send me a CRF value (0–51):")

    elif action == 'preset':
        SettingsManager.set(uid, 'preset', val)
        cfg = SettingsManager.get(uid)
        # finalize and show summary
        summary = (
            "✅ **Settings saved!**\n\n"
            f"• Resolution: `{cfg['resolution']}`\n"
            f"• FPS:        `{cfg['fps']}`\n"
            f"• Codec:      `{cfg['codec']}`\n"
            f"• CRF:        `{cfg['crf']}`\n"
            f"• Preset:     `{cfg['preset']}`\n"
        )
        _PENDING.pop(uid, None)
        await cq.edit_message_text(summary, parse_mode="markdown")

@Client.on_message(filters.text & filters.private)
async def handle_crf_text(client: Client, message):
    """Catch the numeric CRF entry."""
    uid = message.from_user.id
    if _PENDING.get(uid) != 'crf':
        return  # not asking for CRF

    txt = message.text.strip()
    if not txt.isdigit() or not (0 <= int(txt) <= 51):
        return await message.reply("❌ Please enter a number between 0 and 51.")

    SettingsManager.set(uid, 'crf', txt)
    _PENDING[uid] = 'preset'
    await message.reply(
        "Finally, choose your encoding preset:",
        reply_markup=_keyboard(PRESETS, 'preset')
    )
