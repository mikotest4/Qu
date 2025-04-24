# helper_func/queue.py

import asyncio
import uuid
from typing import NamedTuple
from pyrogram.types import Message

class Job(NamedTuple):
    job_id: str
    mode: str           # "soft" or "hard"
    chat_id: int
    vid: str
    sub: str
    status_msg: Message

# global FIFO queue
job_queue: asyncio.Queue[Job] = asyncio.Queue()
