from config import Config
import time
import re
import asyncio

# ← NEW: import the SettingsManager you created
from helper_func.settings_manager import SettingsManager

progress_pattern = re.compile(
    r'(frame|fps|size|time|bitrate|speed)\s*\=\s*(\S+)'
)

def parse_progress(line):
    items = {
        key: value for key, value in progress_pattern.findall(line)
    }
    if not items:
        return None
    return items

async def readlines(stream):
    pattern = re.compile(br'[\r\n]+')

    data = bytearray()
    while not stream.at_eof():
        lines = pattern.split(data)
        data[:] = lines.pop(-1)

        for line in lines:
            yield line

        data.extend(await stream.read(1024))

async def read_stderr(start, msg, process):
    async for line in readlines(process.stderr):
        line = line.decode('utf-8')
        progress = parse_progress(line)
        if progress:
            # Progress bar logic
            now = time.time()
            diff = start - now
            text = 'PROGRESS\n'
            text += f"Size   : {progress['size']}\n"
            text += f"Time   : {progress['time']}\n"
            text += f"Speed  : {progress['speed']}"

            # only update every ~5s
            if round(diff % 5) == 0:
                try:
                    await msg.edit(text)
                except:
                    pass

async def softmux_vid(vid_filename, sub_filename, msg):
    # … your existing softmux_vid code unchanged …
    # (I omitted it here for brevity)
    pass

async def hardmux_vid(vid_filename, sub_filename, msg):
    start = time.time()

    # ← NEW: load this user's saved settings (or fall back to your defaults)
    user_id = msg.from_user.id
    cfg     = SettingsManager.get(user_id)
    res     = cfg.get('resolution', '1920:1080')
    fps     = cfg.get('fps',        'original')
    codec   = cfg.get('codec',      'libx264')
    crf     = cfg.get('crf',        '27')
    preset  = cfg.get('preset',     'faster')

    # build ffmpeg -vf chain
    vf_filters = [f"subtitles={sub_filename}"]
    if res != 'original':
        vf_filters.append(f"scale={res}")
    if fps != 'original':
        vf_filters.append(f"fps={fps}")
    vf_arg = ",".join(vf_filters)

    vid = Config.DOWNLOAD_DIR + '/' + vid_filename
    out_file    = '.'.join(vid_filename.split('.')[:-1])
    output_name = out_file + '1.mp4'
    out_loc     = Config.DOWNLOAD_DIR + '/' + output_name

    # ← UPDATED command to use user’s choices
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

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # progress reporting (your existing logic)
    await asyncio.wait([
        asyncio.create_task(read_stderr(start, msg, process)),
        asyncio.create_task(process.wait())
    ])

    if process.returncode == 0:
        await msg.edit(
            f"Muxing Completed Successfully!\n\n"
            f"Time taken: {round(time.time() - start)} seconds"
        )
    else:
        await msg.edit("An Error occurred while Muxing!")
        return False

    # brief pause so user can read
    await asyncio.sleep(2)
    return output_name
