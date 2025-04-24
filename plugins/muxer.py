# plugins/muxer.py

from pyrogram import Client, filters
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

# ------------------------------------------------------------------------------
# only allow configured users
# ------------------------------------------------------------------------------
async def _check_user(filt, client, message):
    return str(message.from_user.id) in Config.ALLOWED_USERS
check_user = filters.create(_check_user)


# ------------------------------------------------------------------------------
# enqueue a soft-mux job
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def enqueue_soft(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)
    if not vid or not sub:
        txt = ''
        if not vid: txt += 'First send a Video File\n'
        if not sub: txt += 'Send a Subtitle File!'
        return await client.send_message(chat_id, txt)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode='html'
    )

    await job_queue.put(Job(job_id, 'soft', chat_id, vid, sub, status))
    db.erase(chat_id)


# ------------------------------------------------------------------------------
# enqueue a hard-mux job
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def enqueue_hard(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)
    if not vid or not sub:
        txt = ''
        if not vid: txt += 'First send a Video File\n'
        if not sub: txt += 'Send a Subtitle File!'
        return await client.send_message(chat_id, txt)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode='html'
    )

    await job_queue.put(Job(job_id, 'hard', chat_id, vid, sub, status))
    db.erase(chat_id)


# ------------------------------------------------------------------------------
# cancel handler can remove from queue or kill running jobs
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    if len(message.command) != 2:
        return await message.reply("Usage: /cancel <job_id>")
    job_id = message.command[1]

    # 1) try to remove from queue (not yet started)
    removed = False
    new_q = asyncio.Queue()
    while not job_queue.empty():
        job = await job_queue.get()
        if job.job_id == job_id:
            removed = True
            await job.status_msg.edit(
                f"❌ Job <code>{job_id}</code> cancelled before start.",
                parse_mode='html'
            )
        else:
            await new_q.put(job)
        job_queue.task_done()
    # restore remaining jobs
    while not new_q.empty():
        await job_queue.put(await new_q.get())

    if removed:
        return

    # 2) otherwise kill if running
    entry = running_jobs.get(job_id)
    if not entry:
        return await message.reply(f"No job `{job_id}` found.", parse_mode='html')

    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()
    running_jobs.pop(job_id, None)
    await message.reply(f"🛑 Job `{job_id}` aborted.", parse_mode='html')


# ------------------------------------------------------------------------------
# background worker that runs one job at a time
# ------------------------------------------------------------------------------
async def queue_worker(client: Client):
    while True:
        job = await job_queue.get()

        # update status → starting
        await job.status_msg.edit(
            f"▶️ Starting <code>{job.job_id}</code> ({job.mode}-mux)…",
            parse_mode='html'
        )

        # run the actual mux
        if job.mode == 'soft':
            _out = await softmux_vid(job.vid, job.sub, job.status_msg)
        else:
            _out = await hardmux_vid(job.vid, job.sub, job.status_msg)

        # if mux succeeded, upload using the same status_msg
        if _out:
            final = db.get_filename(job.chat_id)
            os.rename(
                os.path.join(Config.DOWNLOAD_DIR, _out),
                os.path.join(Config.DOWNLOAD_DIR, final)
            )
            start = time.time()
            if job.mode == 'soft':
                await client.send_document(
                    job.chat_id,
                    document=os.path.join(Config.DOWNLOAD_DIR, final),
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, start, job.job_id)
                )
            else:
                await client.send_video(
                    job.chat_id,
                    video=os.path.join(Config.DOWNLOAD_DIR, final),
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, start, job.job_id)
                )
            await job.status_msg.edit(
                f"✅ Done in {round(time.time() - start)}s",
            )
            # cleanup files & DB
            for fn in (job.vid, job.sub, final):
                try: os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
                except: pass
            db.erase(job.chat_id)

        job_queue.task_done()


