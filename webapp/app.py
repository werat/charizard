#!/usr/bin/env python3

import datetime
import functools
import io
import itertools
import json
import os

from flask import Flask, request, render_template, redirect, url_for, Response


app = Flask(__name__)
db = None

# ensure that admin pass is set
assert 'CHARIZARD_ADMIN_PASS' in os.environ
# either resolve file or use value as is
if os.path.isfile(os.environ['CHARIZARD_ADMIN_PASS']):
    CHARIZARD_ADMIN_PASS = io.open(os.environ['CHARIZARD_ADMIN_PASS'], encoding='utf8').read()
else:
    CHARIZARD_ADMIN_PASS = os.environ['CHARIZARD_ADMIN_PASS']


def format_dt(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def parse_dt(dt):
    return datetime.datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')


def check_auth(username, password):
    return username == 'werat' and password == CHARIZARD_ADMIN_PASS


def authenticate():
    return Response('Could not verify your access level for that URL.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@app.template_filter('pretty_json')
def pretty_json(value):
    return json.dumps(value, sort_keys=True, indent=4, separators=(',', ': '), ensure_ascii=False)


def max_element(iterable, default=None):
    max_el = default
    for element in iterable:
        if element > max_el:
            max_el = element
    return max_el


class Database(object):
    def __init__(self, students_path, db_path):
        self.students_path = students_path
        self.db_path = db_path

    def get_students(self):
        result = []
        if os.path.isfile(self.students_path):
            for line in io.open(self.students_path, encoding='utf8'):
                line = line.strip()
                if line and not line.startswith('#'):
                    result.append(line)
        return result

    def write_event(self, event):
        with io.open(self.db_path, 'a+', encoding='utf8') as db:
            db.write(json.dumps(event, ensure_ascii=False) + '\n')

    def get_events(self, name=None):
        if not os.path.isfile(self.db_path):
            return

        for line in io.open(self.db_path, encoding='utf8'):
            event = json.loads(line)

            if name is None or event['name'] == name:
                yield event

    def get_grouped_events(self):
        def event(e):
            return {k: e[k] for k in ['datetime', 'comment', 'lab', 'bonus-points']}

        events = sorted(self.get_events(), key=lambda e: (e['name'], parse_dt(e['datetime'])))
        events = {k: list(map(event, g)) for k, g in itertools.groupby(events, key=lambda e: e['name'])}

        for name in self.get_students():
            if name not in events:
                continue
            yield name, events[name]

    def get_total_labs(self):
        return max_element((e['lab'] for e in self.get_events()), default=0)

    def get_students_labs(self):
        for name, events in self.get_grouped_events():
            labs = {}
            for event in events:
                lab = event['lab']
                bonus_points = event['bonus-points']
                labs[lab] = max(labs.get(lab, 0), bonus_points)

            yield name, labs


# ensure db is set
assert 'CHARIZARD_DB' in os.environ
db = Database(os.path.join(os.environ['CHARIZARD_DB'], 'students.txt'),
              os.path.join(os.environ['CHARIZARD_DB'], 'db.json'))


@app.route('/', methods=['GET'])
@app.route('/index', methods=['GET'])
def index():
    total_labs = db.get_total_labs()
    students_labs = db.get_students_labs()
    return render_template('index.html', total_labs=total_labs, students_labs=students_labs)


@app.route('/events', methods=['GET'])
def events():
    return render_template('events.html', grouped_events=db.get_grouped_events())


@app.route('/csv', methods=['GET'])
def csv():
    total_labs = db.get_total_labs()
    students_labs = db.get_students_labs()

    header = 'Студент,' + ','.join('Лаба №{}'.format(_+1) for _ in range(total_labs))
    data = []
    for name, labs in students_labs:
        line = name + ',' + ','.join(str(labs.get(_+1, '')) for _ in range(total_labs))
        data.append(line)
    return (header + '\n' + '\n'.join(data) + '\n').encode('utf8')


@app.route('/admin', methods=['GET'])
@requires_auth
def admin():
    return render_template('admin.html')


@app.route('/submit', methods=['POST'])
@requires_auth
def submit():
    event = {
        'name': request.form['name'],
        'lab': int(request.form['lab']),
        'bonus-points': int(request.form['bonus-points']),
        'comment': list(filter(None, (l.strip() for l in request.form['comment'].split('\n')))),
        'datetime': format_dt(datetime.datetime.utcnow()),
    }
    db.write_event(event)

    return redirect(url_for('admin'))


@app.route('/api/students', methods=['GET'])
def api_students():
    return json.dumps(db.get_students())


@app.route('/api/students/<name>', methods=['GET'])
def api_students_events(name):
    return json.dumps(list(db.get_events(name)))


@app.route('/api/validation', methods=['GET'])
def api_validation():
    if request.args['name'] not in db.get_students():
        return 'There is no such student', 400
    return '', 200


if __name__ == '__main__':
    app.run('localhost', port=8080, debug=True)
