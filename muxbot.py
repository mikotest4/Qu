# (c) mohdsabahat

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(message)s - %(levelname)s"
)
logger = logging.getLogger(__name__)

import os
from config import Config
from helper_func.dbhelper import Database as Db

# initialize your database
db = Db().setup()

import pyrogram
# quiet down pyrogram internals
logging.getLogger('pyrogram').setLevel(logging.WARNING)

# import the queue worker you defined in plugins/muxer.py
from plugins.muxer import queue_worker

class QueueBot(pyrogram.Client):
    async def start(self):
        # first do the normal Pyrogram startup
        await super().start()
        # then launch the background queue worker
        self.loop.create_task(queue_worker(self))

if __name__ == '__main__':
    # ensure download directory exists
    if not os.path.isdir(Config.DOWNLOAD_DIR):
        os.mkdir(Config.DOWNLOAD_DIR)

    plugins = dict(root='plugins')

    # use our subclass instead of raw Client
    app = QueueBot(
        'Subtitle Muxer',
        bot_token=Config.BOT_TOKEN,
        api_id=Config.APP_ID,
        api_hash=Config.API_HASH,
        plugins=plugins
    )
    app.run()
