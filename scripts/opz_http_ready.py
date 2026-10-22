"""Bounded JSON readiness after an asynchronous nginx configuration reload."""
import argparse
import http.client
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def probe_once(url: str, host: str, timeout: float) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={'Host': host})
    try:
        with opener.open(request, timeout=timeout) as response:
            media_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            body = response.read(65537)
            result = {'status': response.status, 'ready': False}
            if response.status == 200 and len(body) <= 65536 and media_type == 'application/json':
                data = json.loads(body)
                result['ready'] = isinstance(data, dict) and data.get('status') == 'ok'
            return result
    except urllib.error.HTTPError as error:
        result = {'status': error.code, 'ready': False}
        error.close()
        return result
    except (OSError, ValueError, http.client.HTTPException) as error:
        return {'status': type(error).__name__, 'ready': False}


def wait_ready(url: str, host: str, timeout: float = 30) -> dict:
    started = time.monotonic()
    deadline = started + timeout
    attempts = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # A process budget also bounds a slow/trickling response body. Use the
        # base interpreter to avoid leaving a Windows venv-launcher descendant.
        command = [getattr(sys, '_base_executable', sys.executable), __file__, url,
                   '--host', host, '--probe', '--timeout', str(min(3, remaining))]
        try:
            process = subprocess.run(command, check=True, capture_output=True, text=True, timeout=remaining)
            result = json.loads(process.stdout)
            attempts.append(result['status'])
        except subprocess.TimeoutExpired:
            attempts.append('total-timeout')
            break
        now = time.monotonic()
        if now >= deadline:
            break
        if result.get('ready') is True:
            return {'ok': True, 'url': url, 'statuses': attempts, 'elapsed_sec': round(now - started, 3)}
        time.sleep(min(0.5, deadline - now))
    raise RuntimeError(f'HTTP readiness failed after {timeout}s: {url}; observations={attempts}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--host', required=True)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    function = probe_once if args.probe else wait_ready
    print(json.dumps(function(args.url, args.host, args.timeout), sort_keys=True))
