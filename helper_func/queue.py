
import asyncio
import uuid
from typing import NamedTuple
from pyrogram.types import Message

class Job(NamedTuple):
    job_id: str         # unique short ID
    mode: str           # "soft" or "hard"
    chat_id: int
    vid: str            # input video filename
    sub: str            # input subtitle filename
    font: str           # input font filename
    final_name: str     # the filename to rename→upload
    status_msg: Message # the message we'll keep editing for progress

job_queue: asyncio.Queue[Job] = asyncio.Queue()
