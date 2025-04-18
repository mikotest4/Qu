from config import Config
import time
import re
import asyncio

# ← NEW: import your SettingsManager
from helper_func.settings_manager import SettingsManager

# Progress parsing regex
progress_pattern = re.compile(
    r'(frame|fps|size|time|bitrate|speed)\s*\=\s*(\S+)'
)

def parse_progress(line: str):
    items = { key: value for key, value in progress_pattern.findall(line) }
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
    """Listen to ffmpeg stderr and edit the Telegram message every ~5s."""
    async for raw in readlines(process.stderr):
        line = raw.decode('utf-8', errors='ignore')
        prog = parse_progress(line)
        if not prog:
            continue

        now = time.time()
        diff = now - start
        text = (
            "🔄 <b>Progress</b>\n"
            f"• Size   : {prog.get('size','N/A')}\n"
            f"• Time   : {prog.get('time','N/A')}\n"
            f"• Speed  : {prog.get('speed','N/A')}"
        )

        # update roughly every 5 seconds
        if round(diff) % 5 == 0:
            try:
                await msg.edit(text, parse_mode="HTML")
            except:
                pass

async def softmux_vid(vid_filename: str, sub_filename: str, msg):
    """Stream‐copy mux (MKV) – left untouched from your original."""
    start = time.time()
    vid = f"{Config.DOWNLOAD_DIR}/{vid_filename}"
    sub = f"{Config.DOWNLOAD_DIR}/{sub_filename}"

    out_base = vid_filename.rsplit('.', 1)[0]
    output = f"{out_base}1.mkv"
    out_loc = f"{Config.DOWNLOAD_DIR}/{output}"
    sub_ext = sub_filename.rsplit('.',1)[-1]

    command = [
        'ffmpeg','-hide_banner',
        '-i', vid,
        '-i', sub,
        '-map', '1:0','-map','0',
        '-disposition:s:0','default',
        '-c:v','copy','-c:a','copy',
        '-c:s', sub_ext,
        '-y', out_loc
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
            f"✅ Soft‐Mux completed in {round(time.time() - start)}s",
            parse_mode="HTML"
        )
        await asyncio.sleep(2)
        return output
    else:
        await msg.edit("❌ Error during soft‐muxing!", parse_mode="HTML")
        return False

async def hardmux_vid(vid_filename: str, sub_filename: str, msg):
    """Hard‐mux with subtitles + re‐encode using per‐user settings."""
    start = time.time()

    # ← FIX: use msg.chat.id (bot‐sent messages have no from_user)
    user_id = msg.chat.id
    cfg = SettingsManager.get(user_id)

    # fallbacks to your old defaults
    res    = cfg.get('resolution', '1920:1080')
    fps    = cfg.get('fps',        'original')
    codec  = cfg.get('codec',      'libx264')
    crf    = cfg.get('crf',        '27')
    preset = cfg.get('preset',     'faster')

    # build the -vf chain
    vf_filters = [f"subtitles={sub_filename}"]
    if res != 'original':
        vf_filters.append(f"scale={res}")
    if fps != 'original':
        vf_filters.append(f"fps={fps}")
    vf_arg = ",".join(vf_filters)

    vid = f"{Config.DOWNLOAD_DIR}/{vid_filename}"
    out_base = vid_filename.rsplit('.', 1)[0]
    output_name = f"{out_base}1.mp4"
    out_loc = f"{Config.DOWNLOAD_DIR}/{output_name}"

    command = [
        'ffmpeg', '-hide_banner',
        '-i', vid,
        '-vf', vf_arg,
        '-c:v', codec,
        '-preset', preset,
        '-crf', crf,
        '-map', '0:v:0',
        '-map', '0:a:0?',
        '-c:a', 'copy',
        '-y', out_loc
    ]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # progress reporting
    await asyncio.wait([
        asyncio.create_task(read_stderr(start, msg, proc)),
        asyncio.create_task(proc.wait())
    ])

    if proc.returncode == 0:
        await msg.edit(
            f"✅ Hard‐Mux completed in {round(time.time() - start)}s",
            parse_mode="HTML"
        )
        await asyncio.sleep(2)
        return output_name
    else:
        await msg.edit("❌ Error during hard‐muxing!", parse_mode="HTML")
        return False
