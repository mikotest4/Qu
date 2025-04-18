
import os

class Config:

    BOT_TOKEN = "7306019161:AAEbFoqmnfitv6X-wQpoaa0ztD_-1MGjJ0Q"
    APP_ID = 27999679
    API_HASH = "f553398ca957b9c92bcb672b05557038"

    #comma seperated user id of users who are allowed to use
    ALLOWED_USERS = [x.strip(' ') for x in os.environ.get('ALLOWED_USERS','1423807625,1048110820,6520490787,7100701721,7297547385').split(',')]

    DOWNLOAD_DIR = 'downloads'
