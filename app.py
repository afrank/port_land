
import os
import json
import sys
from flask import Flask, request
import pickle

import boto
import boto.s3.connection

# a range string can be a comma-delimited list of ranges in the 
# format {lower}-{upper}, which is inclusive of {lower} and {upper}
range_string = os.environ.get("RANGE","15000-15001")
state_server = os.environ.get('STATE_SERVER',"s3.amazonaws.com")
state_bucket = os.environ.get('STATE_BUCKET',None)
state_key = os.environ.get('STATE_KEY','number-state')
state_access_key = os.environ.get('STATE_ACCESS_KEY',None)
state_secret_key = os.environ.get('STATE_SECRET_KEY',None)
state_backup_interval = float(os.environ.get('STATE_BACKUP_INTERVAL',600))

app = Flask(__name__)
ranges = range_string.split(',')
ALL = {}
if 'ceph' in state_server:
    calling_format = boto.s3.connection.OrdinaryCallingFormat()
else:
    calling_format = boto.s3.connection.SubdomainCallingFormat()


class Number:
    def __init__(self,number,label):
        self.id = int(number)
        self.available = True
        self.label = str(label)
    def __dict__(self):
        return { 'id': self.id, 'available': self.available, 'label': self.label }
    def reserve(self,label):
        self.available = False
        self.label = str(label)
        save_state()
    def free(self):
        self.available = True
        save_state()

for r in ranges:
    x = r.split('-')
    if len(x) >= 2:
        lower,upper = int(x[0]),int(x[1])
    elif len(x) == 1:
        lower,upper = int(x[0]),int(x[0])
    for _x in range(lower,upper+1):
        ALL[str(_x)] = Number(_x,'')

def connection():
    return boto.connect_s3(
        aws_access_key_id = state_access_key,
        aws_secret_access_key = state_secret_key,
        host = state_server,
        is_secure=False,
        calling_format = calling_format,
    )

def bucket(conn):
    try:
        b = conn.get_bucket(state_bucket)
    except:
        b = None
    if b is None:
        print "Creating bucket %s" % state_bucket
        b = conn.create_bucket(state_bucket)
    return b

def key(bkt,key_name):
    k = bkt.get_key(key_name)
    if k is None:
        print "Creating key %s" % key_name
        k = bkt.new_key(key_name)
    return k

def upload(stuff):
    conn = connection()
    bkt = bucket(conn)
    k = key(bkt,state_key)
    k.set_contents_from_string(pickle.dumps(stuff))
    print "Stuff backed up Successfully."

def download(key_name):
    conn = connection()
    bkt = bucket(conn)
    k = key(bkt,key_name)
    print "Attempting to download key {0}".format(k.name)
    try:
        obj_contents = k.get_contents_as_string()
    except:
        print "Was not able to retrieve key {0}".format(k.name)
        return False
    else:
        return pickle.loads(obj_contents)

def save_state():
    # get all the unavailable numbers from ALL and store them in s3.
    return upload([ (int(ALL[x].id),str(ALL[x].label)) for x in ALL if not ALL[x].available ])

def load_state():
    # get the state from s3 and apply it to your existing objects
    state = download(state_key)
    if not state: return None
    try:
        for x,y in state:
            if str(x) not in ALL:
                ALL[str(x)] = Number(x,y)
            ALL[str(x)].reserve(y)
    except:
        # can't parse state
        pass

@app.route('/', methods=['GET'])
def dump_all():
    load_state()
    x = [ ALL[_x].__dict__ for _x in ALL ]
    return json.dumps(x)

@app.route('/used/', methods=['GET'])
def get_used():
    load_state()
    x = [ ALL[_x].__dict__ for _x in ALL if not ALL[_x].available ]
    return json.dumps(x)

@app.route('/<number>', methods=['GET'])
def is_available(number):
    if str(number) not in ALL:
        # not in range
        return 'NOT IN RANGE', 404
    elif ALL[str(number)].available:
        # in range and available!
        return json.dumps(ALL[str(number)].__dict__), 200
    else:
        # in range, not available
        return json.dumps(ALL[str(number)].__dict__), 500

@app.route('/<number>', methods=['POST'])
def reserve(number):
    if str(number) not in ALL:
        # not in range
        return 'NOT IN RANGE', 404
    if 'label' not in request.form:
        return 'NO LABEL SUPPLIED', 503
    if ALL[str(number)].available:
        # in range and available!
        ALL[str(number)].reserve(request.form['label'])
        return json.dumps(ALL[str(number)].__dict__), 200
    else:
        # number is already taken
        return json.dumps(ALL[str(number)].__dict__), 500

@app.route('/any/', methods=['POST'])
def reserve_any():
    if 'label' not in request.form:
        return 'NO LABEL SUPPLIED', 503
    load_state()
    for x in ALL.keys():
        if ALL[x].available:
            ALL[x].reserve(request.form['label'])
            return json.dumps(ALL[str(x)].__dict__), 200
    return 'NONE FOUND TO RESERVE', 404

@app.route('/<number>', methods=['DELETE'])
def unreserve(number):
    if str(number) not in ALL:
        # not in range
        return 'NOT IN RANGE', 404
    elif ALL[str(number)].available:
        # in range and available, unchanged!
        return json.dumps(ALL[str(number)].__dict__), 203
    else:
        # unreserve
        ALL[str(number)].free()
        return json.dumps(ALL[str(number)].__dict__), 200


# Download the latest state.
load_state()

if __name__ == '__main__':
    app.run(debug=True,host='0.0.0.0')

