from pyrogram import Client, filters
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper import Database as Db
from helper_func.mux import softmux_vid, hardmux_vid, running_jobs
from config import Config
import time
import os

db = Db()

# ------------------------------------------------------------------------------
# only allow configured users
# ------------------------------------------------------------------------------
async def _check_user(filt, client, message):
    chat_id = str(message.from_user.id)
    return chat_id in Config.ALLOWED_USERS

check_user = filters.create(_check_user)

# ------------------------------------------------------------------------------
# /softmux handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def softmux(client, message):
    chat_id = message.from_user.id
    og_vid_filename = db.get_vid_filename(chat_id)
    og_sub_filename = db.get_sub_filename(chat_id)

    if not og_vid_filename or not og_sub_filename:
        text = ''
        if not og_vid_filename:
            text += 'First send a Video File\n'
        if not og_sub_filename:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text)

    sent_msg = await client.send_message(
        chat_id,
        '🔄 Your file is being soft-subbed…'
    )

    # this now returns immediately with a job_id posted to sent_msg
    softmux_filename = await softmux_vid(og_vid_filename, og_sub_filename, sent_msg)
    if not softmux_filename:
        return  # error already shown in softmux_vid

    final_filename = db.get_filename(chat_id)
    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, softmux_filename),
        os.path.join(Config.DOWNLOAD_DIR, final_filename)
    )

    start_time = time.time()
    try:
        await client.send_document(
            chat_id,
            document=os.path.join(Config.DOWNLOAD_DIR, final_filename),
            caption=final_filename,
            progress=progress_bar,
            progress_args=('Uploading your file…', sent_msg, start_time)
        )
        await sent_msg.edit(
            f"✅ File uploaded!\nTotal time: {round(time.time() - start_time)}s"
        )
    except Exception as e:
        print(e)
        await client.send_message(
            chat_id,
            '❌ An error occurred during upload. Check logs for details.'
        )

    # cleanup
    for fn in (og_vid_filename, og_sub_filename, final_filename):
        try:
            os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
        except:
            pass
    db.erase(chat_id)

# ------------------------------------------------------------------------------
# /hardmux handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def hardmux(client, message):
    chat_id = message.from_user.id
    og_vid_filename = db.get_vid_filename(chat_id)
    og_sub_filename = db.get_sub_filename(chat_id)

    if not og_vid_filename or not og_sub_filename:
        text = ''
        if not og_vid_filename:
            text += 'First send a Video File\n'
        if not og_sub_filename:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text)

    sent_msg = await client.send_message(
        chat_id,
        '🔄 Your file is being hard-subbed…'
    )

    hardmux_filename = await hardmux_vid(og_vid_filename, og_sub_filename, sent_msg)
    if not hardmux_filename:
        return  # error already shown in hardmux_vid

    final_filename = db.get_filename(chat_id)
    os.rename(
        os.path.join(Config.DOWNLOAD_DIR, hardmux_filename),
        os.path.join(Config.DOWNLOAD_DIR, final_filename)
    )

    start_time = time.time()
    try:
        await client.send_video(
            chat_id,
            video=os.path.join(Config.DOWNLOAD_DIR, final_filename),
            caption=final_filename,
            progress=progress_bar,
            progress_args=('Uploading your file…', sent_msg, start_time)
        )
        await sent_msg.edit(
            f"✅ File uploaded!\nTotal time: {round(time.time() - start_time)}s"
        )
    except Exception as e:
        print(e)
        await client.send_message(
            chat_id,
            '❌ An error occurred during upload. Check logs for details.'
        )

    # cleanup
    for fn in (og_vid_filename, og_sub_filename, final_filename):
        try:
            os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
        except:
            pass
    db.erase(chat_id)

# ------------------------------------------------------------------------------
# /cancel handler
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    chat_id = message.from_user.id

    # must be exactly "/cancel <job_id>"
    if len(message.command) != 2:
        return await client.send_message(chat_id, "Usage: /cancel <job_id>")

    job_id = message.command[1]
    entry = running_jobs.get(job_id)
    if not entry:
        return await client.send_message(chat_id, f"No active job with ID `{job_id}`")

    proc  = entry['proc']
    tasks = entry['tasks']

    # kill the ffmpeg process and cancel its asyncio tasks
    proc.kill()
    for t in tasks:
        t.cancel()

    # remove from registry so it can’t be canceled again
    running_jobs.pop(job_id, None)

    await client.send_message(chat_id, f"🛑 Job `{job_id}` has been cancelled.")
