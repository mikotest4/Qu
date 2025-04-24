from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from helper_func.queue import Job, job_queue
from helper_func.mux import softmux_vid, hardmux_vid, running_jobs
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper import Database as Db
from config import Config
import uuid
import time
import os
import asyncio

db = Db()

async def _check_user(filt, client, message):
    return str(message.from_user.id) in Config.ALLOWED_USERS
check_user = filters.create(_check_user)


# ------------------------------------------------------------------------------
# enqueue soft-mux — do NOT clear the DB here
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def enqueue_soft(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)

    if not vid or not sub:
        text = ''
        if not vid:
            text += 'First send a Video File\n'
        if not sub:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'soft', chat_id, vid, sub, status))


# ------------------------------------------------------------------------------
# enqueue hard-mux — do NOT clear the DB here
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def enqueue_hard(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)

    if not vid or not sub:
        text = ''
        if not vid:
            text += 'First send a Video File\n'
        if not sub:
            text += 'Send a Subtitle File!'
        return await client.send_message(chat_id, text, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'hard', chat_id, vid, sub, status))


# ------------------------------------------------------------------------------
# cancel a single job (pending or running)
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    if len(message.command) != 2:
        return await message.reply_text(
            "Usage: /cancel <job_id>",
            parse_mode=ParseMode.HTML
        )

    job_id = message.command[1]

    # 1) remove from queue if it's still pending
    removed = False
    temp_q = asyncio.Queue()
    while not job_queue.empty():
        job = await job_queue.get()
        if job.job_id == job_id:
            removed = True
            await job.status_msg.edit(
                f"❌ Job <code>{job_id}</code> cancelled before start.",
                parse_mode=ParseMode.HTML
            )
        else:
            await temp_q.put(job)
        job_queue.task_done()
    # restore remaining jobs
    while not temp_q.empty():
        await job_queue.put(await temp_q.get())

    if removed:
        return

    # 2) otherwise, if it's running, kill it
    entry = running_jobs.get(job_id)
    if not entry:
        return await message.reply_text(
            f"No job `<code>{job_id}</code>` found.",
            parse_mode=ParseMode.HTML
        )

    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()
    running_jobs.pop(job_id, None)

    await message.reply_text(
        f"🛑 Job `<code>{job_id}</code>` aborted.",
        parse_mode=ParseMode.HTML
    )


# ------------------------------------------------------------------------------
# single worker that processes jobs one-by-one
# ------------------------------------------------------------------------------
async def queue_worker(client: Client):
    while True:
        job = await job_queue.get()

        # mark as starting
        await job.status_msg.edit(
            f"▶️ Starting <code>{job.job_id}</code> ({job.mode}-mux)...",
            parse_mode=ParseMode.HTML
        )

        # run mux (this will itself show live progress including job_id)
        out_file = await (
            softmux_vid if job.mode == 'soft' else hardmux_vid
        )(job.vid, job.sub, job.status_msg)

        # if it succeeded, rename & upload
        if out_file:
            final_name = db.get_filename(job.chat_id)
            src = os.path.join(Config.DOWNLOAD_DIR, out_file)
            dst = os.path.join(Config.DOWNLOAD_DIR, final_name)
            os.rename(src, dst)

            start_ts = time.time()
            if job.mode == 'soft':
                await client.send_document(
                    job.chat_id,
                    document=dst,
                    caption=final_name,
                    progress=progress_bar,
                    progress_args=('Uploading...', job.status_msg, start_ts, job.job_id)
                )
            else:
                await client.send_video(
                    job.chat_id,
                    video=dst,
                    caption=final_name,
                    progress=progress_bar,
                    progress_args=('Uploading...', job.status_msg, start_ts, job.job_id)
                )

            await job.status_msg.edit(
                f"✅ Job <code>{job.job_id}</code> done in {round(time.time() - start_ts)}s",
                parse_mode=ParseMode.HTML
            )

            # cleanup local files
            for fn in (job.vid, job.sub, final_name):
                try:
                    os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
                except:
                    pass

            # only now erase the DB entry
            db.erase(job.chat_id)

        # mark job as done so queue moves on
        job_queue.task_done()
