"""Local-only demo server. Run: python3 server.py"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from threading import Lock
from planner.agents import assess, find_prices, plan_recipes, plan_workouts, replace_meal

ROOT = Path(__file__).parent
SESSIONS = {}
LOCK = Lock()
ALLOWED_ORIGINS = {None, 'http://localhost:8000', 'http://127.0.0.1:8000'}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, content_type='application/json'):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path != '/':
            return self.reply(404, {'error': 'Not found'})
        body = (ROOT / 'web/index.html').read_bytes()
        self.reply(200, body, 'text/html; charset=utf-8')

    def read_json(self):
        size = int(self.headers.get('Content-Length', 0))
        if not 0 < size <= 16384:
            raise ValueError('Invalid request size.')
        data = json.loads(self.rfile.read(size))
        if not isinstance(data, dict):
            raise ValueError('Request must be an object.')
        return data

    def session(self, data):
        token = data.get('session_id')
        if not isinstance(token, str) or token not in SESSIONS:
            raise ValueError('Find recipes first. The plan resets when the server restarts.')
        return token

    def do_POST(self):
        # No cross-origin writes to the local demo.
        if self.headers.get('Origin') not in ALLOWED_ORIGINS:
            return self.reply(403, {'error': 'Origin not allowed'})
        path = urlparse(self.path).path
        try:
            data = self.read_json()
            if path == '/api/assess':
                return self.reply(200, assess(data))
            with LOCK:
                if path == '/api/recipes':
                    token = data.get('session_id')
                    old = SESSIONS.get(token, {}) if isinstance(token, str) else {}
                    rejected = old.get('rejected_recipe_ids', []) if data.get('remember_preferences', True) else []
                    body = data.get('body')
                    if not isinstance(body, dict):
                        raise ValueError('Enter your stats before planning meals.')
                    assessment = assess(body)
                    goals = {goal['id']: goal for goal in assessment['goals']}
                    goal = data.get('goal', 'maintenance')
                    if goal not in goals:
                        raise ValueError('Goal must be maintenance, cutting, or bulking.')
                    plan = plan_recipes({
                        'daily_calories': goals[goal]['calories'],
                        'weekly_budget': data.get('weekly_budget'),
                        'diet': data.get('diet', 'any'),
                        'allergens': data.get('allergens', []),
                        'equipment': 'home',
                        'workout_days': [],
                        'goal': goal,
                        'macro_split': data.get('macro_split', 'moderate'),
                    }, rejected, assessment)
                    token = token if old else secrets.token_urlsafe(24)
                elif path == '/api/replace':
                    token = self.session(data)
                    plan = replace_meal(SESSIONS[token], data.get('day'), data.get('slot'))
                elif path == '/api/prices':
                    token = self.session(data)
                    plan = find_prices(SESSIONS[token])
                elif path == '/api/workouts':
                    token = self.session(data)
                    plan = plan_workouts(SESSIONS[token], data.get('equipment'), data.get('workout_days'))
                else:
                    return self.reply(404, {'error': 'Not found'})
                SESSIONS[token] = plan
            self.reply(200, {'session_id': token, 'plan': plan})
        except (ValueError, TypeError, KeyError) as error:
            self.reply(400, {'error': str(error)})


if __name__ == '__main__':
    print('Open http://localhost:8000 — Ctrl+C to stop')
    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
