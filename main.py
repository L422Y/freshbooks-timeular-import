from requests import request
from os import getenv
from json import loads, dumps
from dotenv import load_dotenv
from pathlib import Path
from freshbooks import Client
from datetime import datetime, time as datetime_time, timedelta
import sys

if sys.version_info < (3, 6):
    sys.exit('Python 3.6 or later is required.')

load_dotenv()
freshBooksClient = None
lastId = 0
ts_format = '%Y-%m-%dT%H:%M:%S.%f'

if Path('lastID').exists():
    lastId = int(Path('lastID').read_text())

# FRESHBOOKS
fb_id = getenv('FB_CLIENT_ID')
fb_secret = getenv('FB_CLIENT_SECRET')
fb_redirect_uri = getenv('FB_REDIR_URI')

if Path('.fb_refresh_token').exists():
    fb_refresh_token = Path('.fb_refresh_token').read_text()
    freshBooksClient = Client(
        client_id=fb_id,
        client_secret=fb_secret,
        refresh_token=fb_refresh_token,
        redirect_uri=fb_redirect_uri
    )
    auth_results = freshBooksClient.refresh_access_token(fb_refresh_token)
    Path('.fb_refresh_token').write_text(auth_results.refresh_token)
else:
    freshBooksClient = Client(
        client_id=fb_id,
        client_secret=fb_secret,
        redirect_uri=fb_redirect_uri
    )

    auth_url = freshBooksClient.get_auth_request_url([
        'user:profile:read',
        'user:time_entries:write',
        'user:time_entries:read',
        'user:projects:read',
        'user:clients:read'
    ])

    print('Go to this URL to authorize: %s' % auth_url)
    auth_code = input('Enter the code you get after authorization: ')
    token_response = freshBooksClient.get_access_token(auth_code)

    print('This is the access token the client is now configurated with: %s' % token_response.access_token)
    print('It is good until %s' % token_response.access_token_expires_at)
    print()

    Path('.fb_refresh_token').write_text(token_response.refresh_token)

identity = freshBooksClient.current_user()
biz = identity.business_memberships[0].business
business_id = biz.id
account_id = biz.account_id


# TIMEULAR

# auth / get token
def get_timeular_token():
    url = 'https://api.timeular.com/api/v3/developer/sign-in'
    response = request(
        'POST', url,
        headers={'Content-Type': 'application/json'},
        data=dumps({
            "apiKey": getenv('TIMEULAR_KEY'),
            "apiSecret": getenv('TIMEULAR_SECRET')
        })
    )
    return loads(response.text)['token']


# get entries
def get_timeular_entries(begin, end):
    response = request(
        'GET',
        'https://api.timeular.com/api/v2/time-entries/%sT00:00:00.000/%sT00:00:00.000' % (begin, end),
        headers={'Authorization': 'Bearer %s' % get_timeular_token()}
    )
    items = loads(response.text)['timeEntries']
    return items.sort(key=lambda x: x['duration']['startedAt'])


# calculate difference between timestamps
def time_diff(start, end):
    if isinstance(start, datetime_time):  # convert to datetime
        assert isinstance(end, datetime_time)
        start, end = [datetime.combine(datetime.min, t) for t in [start, end]]
    if start <= end:
        return end - start
    else:
        end += timedelta(1)  # +day
        assert end > start
        return end - start


entries = get_timeular_entries(getenv('START_DATE'), getenv('END_DATE'))

if entries and 0 < len(entries):
    biggestId = lastId
    for te in entries:
        if int(lastId) < int(te['id']):
            task_start = datetime.strptime(te['duration']['startedAt'], ts_format)
            task_end = datetime.strptime(te['duration']['stoppedAt'], ts_format)
            dur = time_diff(task_start, task_end)
            freshBooksClient.time_entries \
                .create(business_id=business_id,
                        data={
                            "is_logged": True,
                            "duration": dur.total_seconds(),
                            "note": "# %s - %s" % (te['activity']['name'], te['note']['text']),
                            "started_at": te['duration']['startedAt'],
                            "billable": True,
                            "billed": False,
                            "identity_id": freshBooksClient.current_user().identity_id,
                        })
            print("%s\t%s\t%s\t%s - %s" % (
                task_start.date(),
                te['id'],
                str(dur).ljust(20, ' '),
                te['activity']['name'],
                te['note']['text'])
                  )
            if int(te['id']) > biggestId:
                biggestId = int(te['id'])

            Path('lastID').write_text(str(biggestId))
else:
    print('No new entries since last run.')
