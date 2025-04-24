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


@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def enqueue_soft(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)
    if not vid or not sub:
        txt = ''
        if not vid: txt += 'First send a Video File\n'
        if not sub: txt += 'Send a Subtitle File!'
        return await client.send_message(
            chat_id, txt, parse_mode=ParseMode.HTML
        )

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'soft', chat_id, vid, sub, status))
    db.erase(chat_id)


@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def enqueue_hard(client, message):
    chat_id = message.from_user.id
    vid     = db.get_vid_filename(chat_id)
    sub     = db.get_sub_filename(chat_id)
    if not vid or not sub:
        txt = ''
        if not vid: txt += 'First send a Video File\n'
        if not sub: txt += 'Send a Subtitle File!'
        return await client.send_message(
            chat_id, txt, parse_mode=ParseMode.HTML
        )

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'hard', chat_id, vid, sub, status))
    db.erase(chat_id)


@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    if len(message.command) != 2:
        return await message.reply_text(
            "Usage: /cancel <job_id>", parse_mode=ParseMode.HTML
        )
    job_id = message.command[1]

    # 1) remove from queue if pending
    removed = False
    new_q = asyncio.Queue()
    while not job_queue.empty():
        job = await job_queue.get()
        if job.job_id == job_id:
            removed = True
            await job.status_msg.edit(
                f"❌ Job <code>{job_id}</code> cancelled before start.",
                parse_mode=ParseMode.HTML
            )
        else:
            await new_q.put(job)
        job_queue.task_done()
    while not new_q.empty():
        await job_queue.put(await new_q.get())

    if removed:
        return

    # 2) kill running job if active
    entry = running_jobs.get(job_id)
    if not entry:
        return await message.reply_text(
            f"No job `<code>{job_id}</code>` found.", parse_mode=ParseMode.HTML
        )

    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()
    running_jobs.pop(job_id, None)

    await message.reply_text(
        f"🛑 Job <code>{job_id}</code> aborted.", parse_mode=ParseMode.HTML
    )


@Client.on_message(filters.command('queue') & check_user & filters.private)
async def list_queue(client, message):
    if job_queue.empty():
        return await message.reply_text(
            "📭 The queue is empty.", parse_mode=ParseMode.HTML
        )

    text = "🗒️ Pending jobs:\n\n"
    for pos, job in enumerate(job_queue._queue, start=1):
        text += (
            f"{pos}. <code>{job.job_id}</code> "
            f"({job.mode}-mux)\n"
        )
    await message.reply_text(text, parse_mode=ParseMode.HTML)


@Client.on_message(filters.command('cancel_all') & check_user & filters.private)
async def cancel_all(client, message):
    count = 0
    while not job_queue.empty():
        job = await job_queue.get()
        await job.status_msg.edit(
            f"❌ Job <code>{job.job_id}</code> cancelled before start.",
            parse_mode=ParseMode.HTML
        )
        job_queue.task_done()
        count += 1
    await message.reply_text(
        f"🛑 Cancelled {count} queued job{'s' if count != 1 else ''}.",
        parse_mode=ParseMode.HTML
    )


@Client.on_message(filters.command('skip') & check_user & filters.private)
async def skip_current(client, message):
    if not running_jobs:
        return await message.reply_text(
            "🚦 No job is currently running.", parse_mode=ParseMode.HTML
        )

    job_id, entry = next(iter(running_jobs.items()))
    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()
    running_jobs.pop(job_id, None)

    await message.reply_text(
        f"⏭️ Skipped job <code>{job_id}</code>. Next will start soon.",
        parse_mode=ParseMode.HTML
    )


async def queue_worker(client: Client):
    while True:
        job = await job_queue.get()
        await job.status_msg.edit(
            f"▶️ Starting <code>{job.job_id}</code> ({job.mode}-mux)…",
            parse_mode=ParseMode.HTML
        )

        if job.mode == 'soft':
            out = await softmux_vid(job.vid, job.sub, job.status_msg)
        else:
            out = await hardmux_vid(job.vid, job.sub, job.status_msg)

        if out:
            final = db.get_filename(job.chat_id)
            os.rename(
                os.path.join(Config.DOWNLOAD_DIR, out),
                os.path.join(Config.DOWNLOAD_DIR, final)
            )
            t0 = time.time()
            if job.mode == 'soft':
                await client.send_document(
                    job.chat_id,
                    document=os.path.join(Config.DOWNLOAD_DIR, final),
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0, job.job_id)
                )
            else:
                await client.send_video(
                    job.chat_id,
                    video=os.path.join(Config.DOWNLOAD_DIR, final),
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0, job.job_id)
                )
            await job.status_msg.edit(
                f"✅ Done in {round(time.time() - t0)}s",
                parse_mode=ParseMode.HTML
            )
            for fn in (job.vid, job.sub, final):
                try: os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
                except: pass
            db.erase(job.chat_id)

        job_queue.task_done()
