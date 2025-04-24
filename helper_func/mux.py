from pyrogram import Client, filters
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper import Database as Db
from helper_func.mux import softmux_vid, hardmux_vid, running_jobs
from config import Config
import os
import time

db = Db()

# ------------------------------------------------------------------------------
# only allow configured users
# ------------------------------------------------------------------------------
async def _check_user(filt, client, message):
    return str(message.from_user.id) in Config.ALLOWED_USERS

check_user = filters.create(_check_user)


# ------------------------------------------------------------------------------
# /softmux handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def softmux(client, message):
    chat_id = message.from_user.id
    vid = db.get_vid_filename(chat_id)
    sub = db.get_sub_filename(chat_id)
    if not vid or not sub:
        text = ''
        if not vid:
            text += 'First send a Video File\n'
        if not sub:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text)

    # this message will be edited by softmux_vid() to show job_id & progress
    sent_msg = await client.send_message(chat_id, '🔄 Starting soft-mux…')

    # kicks off ffmpeg, registers the job and edits sent_msg
    result = await softmux_vid(vid, sub, sent_msg)
    if not result:
        return   # softmux_vid already edited with error

    # rename and upload
    final = db.get_filename(chat_id)
    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, result),
        os.path.join(Config.DOWNLOAD_DIR, final)
    )

    t0 = time.time()
    try:
        await client.send_document(
            chat_id,
            document=os.path.join(Config.DOWNLOAD_DIR, final),
            caption=final,
            progress=progress_bar,
            progress_args=('Uploading your file…', sent_msg, t0)
        )
        await sent_msg.edit(f'✅ File uploaded!\nTotal time: {round(time.time()-t0)}s')
    except Exception as e:
        print(e)
        await client.send_message(chat_id, '❌ Upload failed. Check logs.')

    # cleanup
    for fn in (vid, sub, final):
        try: os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
        except: pass
    db.erase(chat_id)


# ------------------------------------------------------------------------------
# /hardmux handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def hardmux(client, message):
    chat_id = message.from_user.id
    vid = db.get_vid_filename(chat_id)
    sub = db.get_sub_filename(chat_id)
    if not vid or not sub:
        text = ''
        if not vid:
            text += 'First send a Video File\n'
        if not sub:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text)

    sent_msg = await client.send_message(chat_id, '🔄 Starting hard-mux…')
    result   = await hardmux_vid(vid, sub, sent_msg)
    if not result:
        return

    final = db.get_filename(chat_id)
    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, result),
        os.path.join(Config.DOWNLOAD_DIR, final)
    )

    t0 = time.time()
    try:
        await client.send_video(
            chat_id,
            video=os.path.join(Config.DOWNLOAD_DIR, final),
            caption=final,
            progress=progress_bar,
            progress_args=('Uploading your file…', sent_msg, t0)
        )
        await sent_msg.edit(f'✅ File uploaded!\nTotal time: {round(time.time()-t0)}s')
    except Exception as e:
        print(e)
        await client.send_message(chat_id, '❌ Upload failed. Check logs.')

    for fn in (vid, sub, final):
        try: os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
        except: pass
    db.erase(chat_id)


# ------------------------------------------------------------------------------
# /cancel handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    chat_id = message.from_user.id
    if len(message.command) != 2:
        return await client.send_message(chat_id, 'Usage: /cancel <job_id>')

    job_id = message.command[1]
    entry  = running_jobs.get(job_id)
    if not entry:
        return await client.send_message(chat_id, f'No active job `{job_id}` found.')

    # terminate ffmpeg + cancel our progress tasks
    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()

    # remove from registry
    running_jobs.pop(job_id, None)

    await client.send_message(chat_id, f'🛑 Job `{job_id}` has been cancelled.')
