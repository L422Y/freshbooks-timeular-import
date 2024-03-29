import pprint

from freshbooks import Client
from pathlib import Path
from requests import request
from os import getenv
from json import loads, dumps
from dotenv import load_dotenv
from datetime import datetime, time as datetime_time, timedelta
from sqlite3 import connect
import sys

load_dotenv()
ts_format = '%Y-%m-%dT%H:%M:%S.%f'

dbPath = Path('timeular.sqlite3')
db = connect(dbPath)
c = db.cursor()
c.execute('CREATE TABLE IF NOT EXISTS processed_items (id int, date text, activity_id int)')


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


def init_freshbooks_client():
    fb_id = getenv('FB_CLIENT_ID')
    fb_secret = getenv('FB_CLIENT_SECRET')
    fb_redirect_uri = getenv('FB_REDIR_URI')

    if Path('.fb_refresh_token').exists():
        fb_refresh_token = Path('.fb_refresh_token').read_text()
        freshbooks_client = Client(
            client_id=fb_id,
            client_secret=fb_secret,
            refresh_token=fb_refresh_token,
            redirect_uri=fb_redirect_uri
        )
        auth_results = freshbooks_client.refresh_access_token(fb_refresh_token)
        Path('.fb_refresh_token').write_text(auth_results.refresh_token)
    else:
        freshbooks_client = Client(
            client_id=fb_id,
            client_secret=fb_secret,
            redirect_uri=fb_redirect_uri
        )

        auth_url = freshbooks_client.get_auth_request_url([
            'user:profile:read',
            'user:time_entries:write',
            'user:time_entries:read',
            'user:projects:read',
            'user:clients:read'
        ])

        print('Go to this URL to authorize: %s' % auth_url)
        auth_code = input('Enter the code you get after authorization: ')
        token_response = freshbooks_client.get_access_token(auth_code)

        print('This is the access token the client is now configurated with: %s' % token_response.access_token)
        print('It is good until %s' % token_response.access_token_expires_at)
        print()

        Path('.fb_refresh_token').write_text(token_response.refresh_token)

    return freshbooks_client


def send_entries_to_freshbooks(freshbooks_client, activities, entries):
    identity = freshbooks_client.current_user()
    biz = identity.business_memberships[0].business
    business_id = biz.id
    account_id = biz.account_id

    # load map
    activity_map = {}

    if entries and 0 < len(entries):

        if Path('.activitymap.json').exists():
            activity_map = loads(Path('.activitymap.json').read_text())

        for te in entries:
            activity_id = te['activityId']
            entry_id = te['id']

            c.execute('SELECT id FROM processed_items WHERE id = ?', (entry_id,))
            if c.fetchone() is None:
                activity = next((a for a in activities if a['id'] == activity_id), None)

                task_start = datetime.strptime(te['duration']['startedAt'], ts_format)
                task_end = datetime.strptime(te['duration']['stoppedAt'], ts_format)
                dur = time_diff(task_start, task_end)
                data = {
                    "is_logged": True,
                    "duration": dur.total_seconds(),
                    "note": "# %s - %s" % (activity['name'], te['note']['text']),
                    "started_at": te['duration']['startedAt'],
                    "billable": True,
                    "billed": False,
                    "identity_id": freshbooks_client.current_user().identity_id,
                }

                if activity_id in activity_map:
                    data['client_id'] = str(activity_map[activity_id])
                else:
                    print('No mapping for %s (%s)' % te['activity']['name'], activity_id)

                freshbooks_client.time_entries.create(business_id=business_id, data=data)
                print("%s\t%s\t%s\t%s - %s" % (
                    task_start.date(),
                    te['id'],
                    str(dur).ljust(20, ' '),
                    activity['name'],
                    te['note']['text'])
                      )
                try:
                    c.execute('INSERT INTO processed_items (id, date, activity_id) VALUES (?, ?, ?)',
                              (te['id'], task_start.date(), activity_id))
                    db.commit()
                except Exception as e:
                    print(e)
    else:
        print('No new entries since last run.')


def get_timeular_activities(token):
    response = request(
        'GET',
        'https://api.timeular.com/api/v3/activities',
        headers={'Authorization': 'Bearer %' % token}
    )
    items = loads(response.text)['activities']
    return items


def get_timeular_entries(token, begin, end):
    response = request(
        'GET',
        'https://api.timeular.com/api/v3/time-entries/%sT00:00:00.000/%sT00:00:00.000' % (begin, end),
        headers={'Authorization': 'Bearer %s' % token}
    )

    pprint.pp(response.text)
    items = loads(response.text)['timeEntries']
    items.sort(key=lambda x: x['duration']['startedAt'])
    return items


def get_timeular_activities(token):
    response = request(
        'GET',
        'https://api.timeular.com/api/v3/activities',
        headers={'Authorization': 'Bearer %s' % token}
    )
    items = loads(response.text)['activities']
    return items


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
