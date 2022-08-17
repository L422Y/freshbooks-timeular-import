import pprint
import sys
from os import getenv
from freshbooks import FilterBuilder
from dotenv import load_dotenv
from pathlib import Path
from json import dumps
from common import init_freshbooks_client, get_timeular_token, get_timeular_activities

if sys.version_info < (3, 6):
    sys.exit('Python 3.6 or later is required.')

load_dotenv()

freshbooks_client = init_freshbooks_client()
timeular_token = get_timeular_token()

identity = freshbooks_client.current_user()
biz = identity.business_memberships[0].business
business_id = biz.id
account_id = biz.account_id
client_user_id = identity.identity_id

fb_filter = FilterBuilder()
fb_filter.boolean("active", True)
clients = freshbooks_client.clients.list(account_id, builders=[fb_filter])
clients = clients.data['clients']

activities = get_timeular_activities(timeular_token)

activity_map = {}

print("Mapping Timeular Activities...")
for a in activities:
    print("'%s' belongs to:" % (a['name']))
    for idx, c in enumerate(clients):
        print("%d) %s" % (idx, c['organization']))
    response = int(input('Enter a number: '))
    picked = clients[response]
    activity_map[a['id']] = picked['id']
    print('%s mapped to %s' % (a['name'], picked['organization']))
    print('----')

pprint.pp(activity_map)

Path('.activitymap.json').write_text(dumps(activity_map))

# TODO: get timeular projects and freshbooks clients and render list to assist in creating a map
