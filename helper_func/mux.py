import os
import time
import re
import uuid
import asyncio
from config import Config
from helper_func.settings_manager import SettingsManager
from pyrogram.enums import ParseMode

running_jobs: dict[str, dict] = {}

progress_pattern = re.compile(r'(frame|fps|size|time|bitrate|speed)\s*=\s*(\S+)')
def parse_progress(line: str):
    items = {k: v for k, v in progress_pattern.findall(line)}
    return items or None

async def readlines(stream):
    pattern = re.compile(br'[\r\n]+')
    data = bytearray()
    while not stream.at_eof():
        parts = pattern.split(data)
        data[:] = parts.pop(-1)
        for line in parts:
            yield line
        data.extend(await stream.read(1024))

async def read_stderr(start: float, msg, proc, job_id: str):
    async for raw in readlines(proc.stderr):
        line = raw.decode(errors='ignore')
        prog = parse_progress(line)
        if not prog:
            continue
        elapsed = time.time() - start
        if round(elapsed) % 5 == 0:
            text = (
                f"🔄 <b>Progress</b> [<code>{job_id}</code>]\n"
                f"• Size   : {prog.get('size','N/A')}\n"
                f"• Time   : {prog.get('time','N/A')}\n"
                f"• Speed  : {prog.get('speed','N/A')}"
            )
            try:
                await msg.edit(text, parse_mode=ParseMode.HTML)
            except:
                pass

async def softmux_vid(vid_filename: str, sub_filename: str, msg):
    # … your existing soft-mux implementation …
    pass

async def hardmux_vid(vid_filename: str, sub_filename: str, msg):
    # … your existing hard-mux implementation …
    pass

# ─────────────────────────────────────────────────────────────────────────────
# NEW: re-encode video WITHOUT subtitles
async def encode_without_sub(vid_filename: str, _sub_unused, msg):
    start = time.time()

    # pull saved settings
    cfg    = SettingsManager.get(msg.chat.id)
    res    = cfg.get('resolution', 'original')
    fps    = cfg.get('fps',        'original')
    codec  = cfg.get('codec',      'libx264')
    crf    = cfg.get('crf',        '27')
    preset = cfg.get('preset',     'faster')

    # build paths
    in_path  = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    base     = os.path.splitext(vid_filename)[0]
    output   = f"{base}_nosub.mkv"
    out_path = os.path.join(Config.DOWNLOAD_DIR, output)

    # build -vf if needed
    vf_args = []
    if res != 'original':
        vf_args.append(f"scale={res}")
    if fps != 'original':
        vf_args.append(f"fps={fps}")
    vf_str = ",".join(vf_args)

    # ffmpeg command
    cmd = [
        'ffmpeg', '-hide_banner',
        '-i', in_path,
        '-c:v', codec, '-crf', crf, '-preset', preset,
        '-c:a', 'copy',
        '-movflags', '+faststart'
    ]
    if vf_str:
        cmd += ['-vf', vf_str]
    cmd += [out_path]

    # launch and track progress
    proc   = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE)
    job_id = uuid.uuid4().hex[:8]
    reader = asyncio.create_task(read_stderr(start, msg, proc, job_id))
    waiter = asyncio.create_task(proc.wait())
    running_jobs[job_id] = {'proc': proc, 'tasks': [reader, waiter]}

    # notify user
    await msg.edit(
        f"🔄 Encode job started: <code>{job_id}</code>\n"
        f"Send <code>/cancel {job_id}</code> to abort",
        parse_mode=ParseMode.HTML
    )

    # wait for completion
    await asyncio.wait([reader, waiter])
    running_jobs.pop(job_id, None)

    if proc.returncode == 0:
        elapsed = round(time.time() - start)
        await msg.edit(
            f"✅ Encode `<code>{job_id}</code>` completed in {elapsed}s",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        return output
    else:
        err = (await proc.stderr.read()).decode(errors='ignore')
        await msg.edit(
            "❌ Error during encode!\n\n"
            f"<pre>{err}</pre>",
            parse_mode=ParseMode.HTML
        )
        return False
