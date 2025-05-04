import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

import os
import time
from chat import Chat
from config import Config
from pyrogram import Client, filters
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper import Database as Db
import re
import requests
from urllib.parse import quote, unquote

db = Db()

async def _check_user(filt, c, m):
    chat_id = str(m.from_user.id)
    return chat_id in Config.ALLOWED_USERS

check_user = filters.create(_check_user)


@Client.on_message(filters.document & check_user & filters.private)
async def save_doc(client, message):
    chat_id    = message.from_user.id
    start_time = time.time()
    downloading = await client.send_message(chat_id, 'Downloading your File!')
    download_location = await client.download_media(
        message=message,
        file_name=Config.DOWNLOAD_DIR + '/',
        progress=progress_bar,
        progress_args=(
            'Initializing',
            downloading,
            start_time
        )
    )

    if download_location is None:
        return client.edit_message_text(
            text='Downloading Failed!',
            chat_id=chat_id,
            message_id=downloading.id
        )

    await client.edit_message_text(
        text=Chat.DOWNLOAD_SUCCESS.format(round(time.time() - start_time)),
        chat_id=chat_id,
        message_id=downloading.id
    )

    tg_filename = os.path.basename(download_location)
    try:
        og_filename = message.document.filename
    except:
        og_filename = False

    save_filename = og_filename or tg_filename
    ext = save_filename.split('.').pop()
    filename = f"{round(start_time)}.{ext}"

    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, tg_filename),
        os.path.join(Config.DOWNLOAD_DIR, filename)
    )

    if ext in ['srt', 'ass']:
        db.put_sub(chat_id, filename)
        if db.check_video(chat_id):
            text = (
                'Subtitle file downloaded successfully.\n'
                'Choose your desired muxing!\n'
                '[ /softmux , /hardmux ]'
            )
        else:
            text = 'Subtitle file downloaded.\nNow send Video File!'

        await client.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=downloading.id
        )

    elif ext in ['mp4', 'mkv']:
        db.put_video(chat_id, filename, save_filename)
        if db.check_sub(chat_id):
            text = (
                'Video file downloaded successfully.\n'
                'Choose your desired muxing.\n'
                '[ /softmux , /hardmux ]'
            )
        else:
            text = (
                'Video file downloaded successfully.\n'
                'Now send Subtitle file!\n'
                'Or send /nosub to encode without subtitles.'
            )

        await client.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=downloading.id
        )

    else:
        text = Chat.UNSUPPORTED_FORMAT.format(ext) + f'\nFile = {tg_filename}'
        await client.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=downloading.id
        )
        os.remove(os.path.join(Config.DOWNLOAD_DIR, tg_filename))


@Client.on_message(filters.video & check_user & filters.private)
async def save_video(client, message):
    chat_id    = message.from_user.id
    start_time = time.time()
    downloading = await client.send_message(chat_id, 'Downloading your File!')
    download_location = await client.download_media(
        message=message,
        file_name=Config.DOWNLOAD_DIR + '/',
        progress=progress_bar,
        progress_args=(
            'Initializing',
            downloading,
            start_time
        )
    )

    if download_location is None:
        return client.edit_message_text(
            text='Downloading Failed!',
            chat_id=chat_id,
            message_id=downloading.id
        )

    await client.edit_message_text(
        text=Chat.DOWNLOAD_SUCCESS.format(round(time.time() - start_time)),
        chat_id=chat_id,
        message_id=downloading.id
    )

    tg_filename = os.path.basename(download_location)
    try:
        og_filename = message.video.file_name
    except:
        og_filename = False

    save_filename = og_filename or tg_filename
    ext = save_filename.split('.').pop()
    filename = f"{round(start_time)}.{ext}"
    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, tg_filename),
        os.path.join(Config.DOWNLOAD_DIR, filename)
    )

    db.put_video(chat_id, filename, save_filename)
    if db.check_sub(chat_id):
        text = (
            'Video file downloaded successfully.\n'
            'Choose your desired muxing.\n'
            '[ /softmux , /hardmux ]'
        )
    else:
        text = (
            'Video file downloaded successfully.\n'
            'Now send Subtitle file!\n'
            'Or send /nosub to encode without subtitles.'
        )

    await client.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=downloading.id
    )


@Client.on_message(filters.text & filters.regex('^http') & check_user)
async def save_url(client, message):
    chat_id      = message.from_user.id
    save_filename = None

    # parse custom filename
    if "|" in message.text and len(message.text.split("|")) == 2:
        url, save_filename = [x.strip() for x in message.text.split("|")]
    else:
        url = message.text.strip()

    # enforce custom filename length
    if save_filename and len(save_filename) > 60:
        return await client.send_message(chat_id, Chat.LONG_CUS_FILENAME)

    # HEAD request to find filename & size
    r = requests.get(url, stream=True, allow_redirects=True)
    if not save_filename:
        # try content-disposition
        cd = r.headers.get("content-disposition", "")
        m  = re.search(r'filename="(.+?)"', cd)
        if m:
            save_filename = m.group(1)
        else:
            save_filename = unquote(url.split("?")[0].split("/")[-1])

    ext = save_filename.split(".")[-1].lower()
    if ext not in ["mp4", "mkv"]:
        return await client.send_message(chat_id, Chat.UNSUPPORTED_FORMAT.format(ext))

    size = int(r.headers.get("content-length", 0))
    if size == 0:
        return await client.send_message(chat_id, Chat.FILE_SIZE_ERROR)
    if size > 2_000_000_000:
        return await client.send_message(chat_id, Chat.MAX_FILE_SIZE)

    # download to disk
    if not os.path.exists(Config.DOWNLOAD_DIR):
        os.makedirs(Config.DOWNLOAD_DIR)

    filename = f"{round(time.time())}.{ext}"
    sent_msg = await client.send_message(chat_id, 'Preparing Your Download')

    current = 0
    start   = time.time()
    with requests.get(url, stream=True, allow_redirects=True) as resp:
        with open(os.path.join(Config.DOWNLOAD_DIR, filename), "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024*1024):
                if chunk:
                    written = f.write(chunk)
                    current += written
                    await progress_bar(current, size, 'Downloading…', sent_msg, start)

    try:
        await sent_msg.edit(Chat.DOWNLOAD_SUCCESS.format(round(time.time() - start)))
    except:
        pass

    db.put_video(chat_id, filename, save_filename)
    if db.check_sub(chat_id):
        text = (
            'Video File Downloaded.\n'
            'Choose your desired muxing\n'
            '[ /softmux , /hardmux ]'
        )
    else:
        text = (
            'Video File Downloaded.\n'
            'Now send Subtitle file!\n'
            'Or send /nosub to encode without subtitles.'
        )

    try:
        await sent_msg.edit(text)
    except:
        pass
