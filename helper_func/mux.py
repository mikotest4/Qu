import os, time, re, uuid, asyncio, shutil
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

async def softmux_vid(vid_filename: str, sub_filename: str, font_filename: str, msg):
    start = time.time()
    vid_path = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    sub_path = os.path.join(Config.DOWNLOAD_DIR, sub_filename)
    font_path = os.path.join(Config.DOWNLOAD_DIR, font_filename)
    base = os.path.splitext(vid_filename)[0]
    output = f"{base}_soft.mkv"
    out_path = os.path.join(Config.DOWNLOAD_DIR, output)
    sub_ext = os.path.splitext(sub_filename)[1].lstrip('.')

    proc = await asyncio.create_subprocess_exec(
        'ffmpeg', '-hide_banner',
        '-i', vid_path, 
        '-i', sub_path, 
        '-attach', font_path,
        '-map', '0', '-map', '1:0',
        '-disposition:s:0', 'default',
        '-c:v', 'copy', '-c:a', 'copy',
        '-c:s', sub_ext,
        '-metadata:s:t:0', f'filename={font_filename}',
        '-metadata:s:t:0', 'mimetype=application/x-truetype-font',
        '-y', out_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    job_id = uuid.uuid4().hex[:8]
    reader = asyncio.create_task(read_stderr(start, msg, proc, job_id))
    waiter = asyncio.create_task(proc.wait())
    running_jobs[job_id] = {'proc': proc, 'tasks': [reader, waiter]}

    await msg.edit(
        f"🔄 Soft-Mux job started: <code>{job_id}</code>\n"
        f"Send <code>/cancel {job_id}</code> to abort",
        parse_mode=ParseMode.HTML
    )

    await asyncio.wait([reader, waiter])
    running_jobs.pop(job_id, None)

    if proc.returncode == 0:
        await msg.edit(
            f"✅ Soft-Mux <code>{job_id}</code> completed in {round(time.time()-start)}s",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        return output
    else:
        err = await proc.stderr.read()
        await msg.edit(
            "❌ Error during soft-mux!\n\n"
            f"<pre>{err.decode(errors='ignore')}</pre>",
            parse_mode=ParseMode.HTML
        )
        return False

async def hardmux_vid(vid_filename: str, sub_filename: str, font_filename: str, msg):
    start = time.time()
    cfg = SettingsManager.get(msg.chat.id)

    res = cfg.get('resolution', '1920:1080')
    fps = cfg.get('fps', 'original')
    codec = cfg.get('codec', 'libx264')
    crf = cfg.get('crf', '27')
    preset = cfg.get('preset', 'faster')

    vid_path = os.path.join(Config.DOWNLOAD_DIR, vid_filename)
    sub_path = os.path.join(Config.DOWNLOAD_DIR, sub_filename)
    font_path = os.path.join(Config.DOWNLOAD_DIR, font_filename)
    
    # Get absolute paths
    vid_path = os.path.abspath(vid_path)
    sub_path = os.path.abspath(sub_path)
    font_path = os.path.abspath(font_path)
    
    # Escape special characters in paths for FFmpeg
    sub_path_escaped = sub_path.replace('\\', '\\\\').replace(':', '\\:')
    font_path_escaped = font_path.replace('\\', '\\\\').replace(':', '\\:')
    
    # Method 1: Try with direct font specification in subtitles filter
    vf_parts = []
    
    # Check subtitle format and use appropriate filter
    sub_ext = os.path.splitext(sub_filename)[1].lower()
    if sub_ext == '.ass':
        # For ASS files, try to force font
        vf_parts.append(f"subtitles={sub_path_escaped}:force_style='FontName={os.path.splitext(font_filename)[0]}'")
    else:
        # For SRT files, use subtitles filter with font directory
        fonts_dir = os.path.join(Config.DOWNLOAD_DIR, 'fonts')
        os.makedirs(fonts_dir, exist_ok=True)
        
        # Copy font to fonts directory
        font_dest = os.path.join(fonts_dir, font_filename)
        shutil.copy2(font_path, font_dest)
        
        fonts_dir_escaped = fonts_dir.replace('\\', '\\\\').replace(':', '\\:')
        vf_parts.append(f"subtitles={sub_path_escaped}:fontsdir={fonts_dir_escaped}")
    
    # Add scaling and fps if needed
    if res != 'original': 
        vf_parts.append(f"scale={res}")
    if fps != 'original': 
        vf_parts.append(f"fps={fps}")
    
    vf_arg = ",".join(vf_parts)

    base = os.path.splitext(vid_filename)[0]
    output = f"{base}_hard.mp4"
    out_path = os.path.join(Config.DOWNLOAD_DIR, output)

    # Build FFmpeg command
    cmd = [
        'ffmpeg', '-hide_banner',
        '-i', vid_path,
        '-vf', vf_arg,
        '-c:v', codec,
        '-preset', preset,
        '-crf', crf,
        '-map', '0:v:0', '-map', '0:a:0?',
        '-c:a', 'copy',
        '-y', out_path
    ]
    
    # Debug: Print the command
    print(f"FFmpeg command: {' '.join(cmd)}")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    job_id = uuid.uuid4().hex[:8]
    reader = asyncio.create_task(read_stderr(start, msg, proc, job_id))
    waiter = asyncio.create_task(proc.wait())
    running_jobs[job_id] = {'proc': proc, 'tasks': [reader, waiter]}

    await msg.edit(
        f"🔄 Hard-Mux job started: <code>{job_id}</code>\n"
        f"Font: {font_filename}\n"
        f"Send <code>/cancel {job_id}</code> to abort",
        parse_mode=ParseMode.HTML
    )

    await asyncio.wait([reader, waiter])
    running_jobs.pop(job_id, None)

    if proc.returncode == 0:
        await msg.edit(
            f"✅ Hard-Mux <code>{job_id}</code> completed in {round(time.time()-start)}s\n"
            f"Font applied: {font_filename}",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(2)
        
        # Clean up fonts directory
        try:
            fonts_dir = os.path.join(Config.DOWNLOAD_DIR, 'fonts')
            if os.path.exists(fonts_dir):
                shutil.rmtree(fonts_dir)
        except:
            pass
            
        return output
    else:
        err = await proc.stderr.read()
        await msg.edit(
            "❌ Error during hard-mux!\n\n"
            f"<pre>{err.decode(errors='ignore')}</pre>",
            parse_mode=ParseMode.HTML
        )
        
        # Clean up fonts directory on error
        try:
            fonts_dir = os.path.join(Config.DOWNLOAD_DIR, 'fonts')
            if os.path.exists(fonts_dir):
                shutil.rmtree(fonts_dir)
        except:
            pass
            
        return False
