import pprint
import sys
from os import getenv
from dotenv import load_dotenv
from common import init_freshbooks_client, get_timeular_entries, send_entries_to_freshbooks, get_timeular_token

if sys.version_info < (3, 6):
    sys.exit('Python 3.6 or later is required.')

load_dotenv()

timeular_token = get_timeular_token()
freshbooks_client = init_freshbooks_client()
entries = get_timeular_entries(timeular_token, getenv('START_DATE'), getenv('END_DATE'))
send_entries_to_freshbooks(freshbooks_client, entries)
