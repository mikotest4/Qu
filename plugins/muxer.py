from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from helper_func.queue import Job, job_queue
from helper_func.mux   import softmux_vid, hardmux_vid, running_jobs
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper       import Database as Db
from config import Config
import uuid, time, os, asyncio

db = Db()

# only allowed users
async def _check_user(filt, client, message):
    return str(message.from_user.id) in Config.ALLOWED_USERS
check_user = filters.create(_check_user)

# enqueue soft-mux
@Client.on_message(filters.command('softmux') & check_user & filters.private)
async def enqueue_soft(client, message):
    vid = db.get_vid_filename(message.from_user.id)
    sub = db.get_sub_filename(message.from_user.id)
    if not vid or not sub:
        txt = ('First send a Video File\n' if not vid else '') + \
              ('Send a Subtitle File!' if not sub else '')
        return await client.send_message(message.chat.id, txt, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        message.chat.id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )
    await job_queue.put(Job(job_id, 'soft', message.chat.id, vid, sub, status))
    db.erase(message.from_user.id)

# enqueue hard-mux
@Client.on_message(filters.command('hardmux') & check_user & filters.private)
async def enqueue_hard(client, message):
    vid = db.get_vid_filename(message.from_user.id)
    sub = db.get_sub_filename(message.from_user.id)
    if not vid or not sub:
        txt = ('First send a Video File\n' if not vid else '') + \
              ('Send a Subtitle File!' if not sub else '')
        return await client.send_message(message.chat.id, txt, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        message.chat.id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )
    await job_queue.put(Job(job_id, 'hard', message.chat.id, vid, sub, status))
    db.erase(message.from_user.id)

# cancel single job (pending or running)
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    if len(message.command) != 2:
        return await message.reply_text("Usage: /cancel <job_id>", parse_mode=ParseMode.HTML)
    job_id = message.command[1]

    # 1) remove from pending queue
    new_q, removed = asyncio.Queue(), False
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

    # 2) kill if already running
    entry = running_jobs.get(job_id)
    if not entry:
        return await message.reply_text(f"No job `<code>{job_id}</code>` found.",
                                        parse_mode=ParseMode.HTML)
    entry['proc'].kill()
    for t in entry['tasks']:
        t.cancel()
    running_jobs.pop(job_id, None)
    await message.reply_text(f"🛑 Job `<code>{job_id}</code>` aborted.",
                             parse_mode=ParseMode.HTML)

# worker that does one job at a time
async def queue_worker(client: Client):
    while True:
        job = await job_queue.get()

        # update to “starting…”
        await job.status_msg.edit(
            f"▶️ Starting <code>{job.job_id}</code> ({job.mode}-mux)…",
            parse_mode=ParseMode.HTML
        )

        # run ffmpeg
        out = await (softmux_vid if job.mode=='soft' else hardmux_vid)(
            job.vid, job.sub, job.status_msg
        )

        # if mux succeeded, rename & upload
        if out:
            final = db.get_filename(job.chat_id)
            src   = os.path.join(Config.DOWNLOAD_DIR, out)
            dst   = os.path.join(Config.DOWNLOAD_DIR, final)
            os.rename(src, dst)

            t0 = time.time()
            if job.mode == 'soft':
                await client.send_document(
                    job.chat_id,
                    document=dst,
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0)
                )
            else:
                await client.send_video(
                    job.chat_id,
                    video=dst,
                    caption=final,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0)
                )

            # final status edit
            await job.status_msg.edit(
                f"✅ Job <code>{job.job_id}</code> done in {round(time.time()-t0)}s",
                parse_mode=ParseMode.HTML
            )

            # cleanup files & DB
            for fn in (job.vid, job.sub, final):
                try: os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
                except: pass
            db.erase(job.chat_id)

        job_queue.task_done()
