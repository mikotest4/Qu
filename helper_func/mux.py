import os
import time
import asyncio
from config import Config
from helper_func.settings_manager import SettingsManager
from pyrogram.enums import ParseMode

# … your parse_progress / read_stderr etc. above …

async def hardmux_vid(vid_filename: str, sub_filename: str, msg):
    """Hard‑mux + re‑encode using per‑user settings, with proper pathing & error surfacing."""
    start = time.time()

    # 1) get user settings
    user_id = msg.chat.id
    cfg     = SettingsManager.get(user_id)
    res    = cfg.get('resolution', '1920:1080')
    fps    = cfg.get('fps',        'original')
    codec  = cfg.get('codec',      'libx264')
    crf    = cfg.get('crf',        '27')
    preset = cfg.get('preset',     'faster')

    # 2) build full paths
    vid_path = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    sub_path = os.path.join(Config.DOWNLOAD_DIR, sub_filename)

    # 3) build -vf filter chain with absolute subtitle path
    vf_filters = [f"subtitles={sub_path}"]
    if res != 'original':
        vf_filters.append(f"scale={res}")
    if fps != 'original':
        vf_filters.append(f"fps={fps}")
    vf_arg = ",".join(vf_filters)

    # 4) output paths
    base = os.path.splitext(vid_filename)[0]
    out_name = f"{base}1.mp4"
    out_path = os.path.join(Config.DOWNLOAD_DIR, out_name)

    # 5) ffmpeg command
    command = [
        'ffmpeg', '-hide_banner',
        '-i', vid_path,
        '-vf', vf_arg,
        '-c:v', codec,
        '-preset', preset,
        '-crf', crf,
        '-map', '0:v:0',
        '-map', '0:a:0?',
        '-c:a', 'copy',
        '-y', out_path
    ]

    # 6) run it
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # still show progress as before
    await asyncio.wait([
        asyncio.create_task(read_stderr(start, msg, proc)),
        asyncio.create_task(proc.wait())
    ])

    # 7) check result & surface real stderr on failure
    if proc.returncode == 0:
        await msg.edit(
            f"✅ Hard‑Mux completed in {round(time.time() - start)}s",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        return out_name
    else:
        err = await proc.stderr.read()
        # show actual ffmpeg error wrapped in <pre>
        text = (
            "❌ Error during hard‑muxing!\n\n"
            f"<pre>{err.decode(errors='ignore')}</pre>"
        )
        await msg.edit(text, parse_mode=ParseMode.HTML)
        return False
