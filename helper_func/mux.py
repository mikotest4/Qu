# helper_func/mux.py

from config import Config
import os
import time
import re
import asyncio

from helper_func.settings_manager import SettingsManager
from pyrogram.enums import ParseMode

# ------------------------------------------------------------------------------
# Progress parsing
# ------------------------------------------------------------------------------
progress_pattern = re.compile(
    r'(frame|fps|size|time|bitrate|speed)\s*=\s*(\S+)'
)

def parse_progress(line: str):
    items = { k: v for k, v in progress_pattern.findall(line) }
    return items or None

async def readlines(stream):
    """Yield lines (bytes) from an asyncio stream."""
    pattern = re.compile(br'[\r\n]+')
    data = bytearray()

    while not stream.at_eof():
        parts = pattern.split(data)
        data[:] = parts.pop(-1)
        for line in parts:
            yield line
        data.extend(await stream.read(1024))

async def read_stderr(start: float, msg, process):
    """Read ffmpeg stderr, parse progress, and edit Telegram msg every ~5s."""
    async for raw in readlines(process.stderr):
        line = raw.decode('utf-8', errors='ignore')
        prog = parse_progress(line)
        if not prog:
            continue

        elapsed = time.time() - start
        text = (
            "🔄 <b>Progress</b>\n"
            f"• Size   : {prog.get('size','N/A')}\n"
            f"• Time   : {prog.get('time','N/A')}\n"
            f"• Speed  : {prog.get('speed','N/A')}"
        )

        # update roughly every 5 seconds
        if round(elapsed) % 5 == 0:
            try:
                await msg.edit(text, parse_mode=ParseMode.HTML)
            except:
                pass

# ------------------------------------------------------------------------------
# Soft‑Mux (stream‑copy into MKV)
# ------------------------------------------------------------------------------
async def softmux_vid(vid_filename: str, sub_filename: str, msg):
    start = time.time()
    vid_path = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    sub_path = os.path.join(Config.DOWNLOAD_DIR, sub_filename)

    base      = os.path.splitext(vid_filename)[0]
    output    = f"{base}_soft.mkv"
    out_path  = os.path.join(Config.DOWNLOAD_DIR, output)
    sub_ext   = os.path.splitext(sub_filename)[1].lstrip('.')

    command = [
        'ffmpeg', '-hide_banner',
        '-i', vid_path,
        '-i', sub_path,
        '-map', '1:0', '-map', '0',
        '-disposition:s:0', 'default',
        '-c:v', 'copy', '-c:a', 'copy',
        '-c:s', sub_ext,
        '-y', out_path
    ]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait([
        asyncio.create_task(read_stderr(start, msg, proc)),
        asyncio.create_task(proc.wait())
    ])

    if proc.returncode == 0:
        await msg.edit(
            f"✅ Soft‑Mux completed in {round(time.time() - start)}s",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        return output
    else:
        err = await proc.stderr.read()
        await msg.edit(
            "❌ Error during soft‑muxing!\n\n"
            f"<pre>{err.decode(errors='ignore')}</pre>",
            parse_mode=ParseMode.HTML
        )
        return False

# ------------------------------------------------------------------------------
# Hard‑Mux (burn‑in subtitles + re‑encode)
# ------------------------------------------------------------------------------
async def hardmux_vid(vid_filename: str, sub_filename: str, msg):
    start = time.time()

    # use chat.id because msg.from_user is None on bot‑sent messages
    user_id = msg.chat.id
    cfg     = SettingsManager.get(user_id)

    # fall back to defaults
    res    = cfg.get('resolution', '1920:1080')
    fps    = cfg.get('fps',        'original')
    codec  = cfg.get('codec',      'libx264')
    crf    = cfg.get('crf',        '27')
    preset = cfg.get('preset',     'faster')

    # build -vf filters (with absolute path to subtitle)
    vid_path = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    sub_path = os.path.join(Config.DOWNLOAD_DIR, sub_filename)
    vf = [f"subtitles={sub_path}"]
    if res != 'original': vf.append(f"scale={res}")
    if fps != 'original': vf.append(f"fps={fps}")
    vf_arg = ",".join(vf)

    base     = os.path.splitext(vid_filename)[0]
    output   = f"{base}_hard.mp4"
    out_path = os.path.join(Config.DOWNLOAD_DIR, output)

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

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.wait([
        asyncio.create_task(read_stderr(start
