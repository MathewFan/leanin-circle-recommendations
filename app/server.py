import argparse
from contextlib import closing
import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.db import DEFAULT_DB, connect
from app.recommend import recommendations


def handler_for(db_path):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/health':
                self.respond(200, {'status': 'ok'})
                return
            match = re.fullmatch(r'/users/([1-9][0-9]*)/recommendations', url.path)
            if not match:
                self.respond(404, {'error': 'Route not found'})
                return
            try:
                params = parse_qs(url.query, keep_blank_values=True)
                if set(params) - {'limit'} or len(params.get('limit', [])) > 1:
                    raise ValueError('Only one limit parameter is supported')
                raw_limit = params.get('limit', ['5'])[0]
                if not re.fullmatch(r'[0-9]{1,2}', raw_limit):
                    raise ValueError('limit must be an integer between 1 and 20')
                with closing(connect(db_path)) as db:
                    result = recommendations(db, int(match[1]), int(raw_limit))
                self.respond(200, result)
            except ValueError as error:
                self.respond(400, {'error': str(error)})
            except LookupError as error:
                self.respond(404, {'error': str(error)})
            except Exception:
                logging.exception('Recommendation request failed')
                self.respond(500, {'error': 'Internal server error'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Circle recommendation API')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default=str(DEFAULT_DB))
    args = parser.parse_args()
    if not Path(args.db).is_file():
        parser.error('Database missing. Run python3 -m app.db first.')
    server = ThreadingHTTPServer((args.host, args.port), handler_for(args.db))
    print(f'Serving http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
