
import os

class Config:

    BOT_TOKEN = "7824226124:AAGH9UkzETijtcxlDTA29FlUSONETvxihCk"
    APP_ID = 27999679
    API_HASH = "f553398ca957b9c92bcb672b05557038"

    #comma seperated user id of users who are allowed to use
    ALLOWED_USERS = [x.strip(' ') for x in os.environ.get('ALLOWED_USERS','1423807625,1048110820,6520490787,7100701721,7297547385').split(',')]

    DOWNLOAD_DIR = 'downloads'
