import asyncio
import uuid
from typing import NamedTuple
from pyrogram.types import Message

class Job(NamedTuple):
    job_id: str       # the short ID
    mode: str         # "soft" or "hard"
    chat_id: int
    vid: str          # input video filename
    sub: str          # input subtitle filename
    status_msg: Message  # the Telegram message we’ll keep editing

# our single FIFO queue
job_queue: asyncio.Queue[Job] = asyncio.Queue()
