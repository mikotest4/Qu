
import os

class Config:

    BOT_TOKEN = "7819249411:AAGzpjJTyVp3Mxu3Px4i1Huk1T5B4daG5hQ"
    APP_ID = "27704224"
    API_HASH = "c2e33826d757fe113bc154fcfabc987d"

    #comma seperated user id of users who are allowed to use
    ALLOWED_USERS = [x.strip(' ') for x in os.environ.get('ALLOWED_USERS','7970350353, 6680407688').split(',')]
 # Absolute path to the folder where you keep your .ttf/.otf files
    FONTS_DIR = os.path.join(os.getcwd(), "fonts")
    
    DOWNLOAD_DIR = 'downloads'
