from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from helper_func.queue import Job, job_queue
from helper_func.mux   import softmux_vid, hardmux_vid, running_jobs
from helper_func.progress_bar import progress_bar
from helper_func.dbhelper       import Database as Db
from config import Config
import uuid, time, os, asyncio

db = Db()

async def _check_user(filt, client, message):
    return str(message.from_user.id) in Config.ALLOWED_USERS
check_user = filters.create(_check_user)

# ------------------------------------------------------------------------------
# enqueue soft-mux — NO db.erase() here!
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
        return await client.send_message(chat_id, txt, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'soft', chat_id, vid, sub, status))
    # <<< no db.erase() here >>>

# ------------------------------------------------------------------------------
# enqueue hard-mux — NO db.erase() here!
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
        return await client.send_message(chat_id, txt, parse_mode=ParseMode.HTML)

    job_id = uuid.uuid4().hex[:8]
    status = await client.send_message(
        chat_id,
        f"🔄 Job <code>{job_id}</code> enqueued at position {job_queue.qsize()+1}",
        parse_mode=ParseMode.HTML
    )

    await job_queue.put(Job(job_id, 'hard', chat_id, vid, sub, status))
    # <<< no db.erase() here >>>

# ------------------------------------------------------------------------------
# cancel handler (unchanged)
# ------------------------------------------------------------------------------
@Client.on_message(filters.command('cancel') & check_user & filters.private)
async def cancel_job(client, message):
    # … your existing cancel logic …
    …

# ------------------------------------------------------------------------------
# the queue worker — only here do we erase the DB after upload
# ------------------------------------------------------------------------------
async def queue_worker(client: Client):
    while True:
        job = await job_queue.get()

        # mark as starting
        await job.status_msg.edit(
            f"▶️ Starting <code>{job.job_id}</code> ({job.mode}-mux)…",
            parse_mode=ParseMode.HTML
        )

        # run ffmpeg
        out_file = await (softmux_vid if job.mode == 'soft' else hardmux_vid)(
            job.vid, job.sub, job.status_msg
        )

        if out_file:
            # get the user’s ORIGINAL filename from DB
            final_name = db.get_filename(job.chat_id)

            # rename our muxed file to that original name
            src = os.path.join(Config.DOWNLOAD_DIR, out_file)
            dst = os.path.join(Config.DOWNLOAD_DIR, final_name)
            os.rename(src, dst)

            # upload with progress
            t0 = time.time()
            if job.mode == 'soft':
                await client.send_document(
                    job.chat_id,
                    document=dst,
                    caption=final_name,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0, job.job_id)
                )
            else:
                await client.send_video(
                    job.chat_id,
                    video=dst,
                    caption=final_name,
                    progress=progress_bar,
                    progress_args=('Uploading…', job.status_msg, t0, job.job_id)
                )

            # final success edit
            await job.status_msg.edit(
                f"✅ Job <code>{job.job_id}</code> done in {round(time.time()-t0)}s",
                parse_mode=ParseMode.HTML
            )

            # cleanup on disk
            for fn in (job.vid, job.sub, final_name):
                try:
                    os.remove(os.path.join(Config.DOWNLOAD_DIR, fn))
                except:
                    pass

            # *** NOW erase the DB entry ***
            db.erase(job.chat_id)

        else:
            # if out_file is False we already showed an error in mux()
            # skip rename/upload
            pass

        job_queue.task_done()
