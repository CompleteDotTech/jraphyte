"""Resumable Gemini Embedding 2 client with atomic reservations and receipts.

No credentials are written to disk. Failed/ambiguous requests retain their
reservation and require an explicit retry; successful inputs are never rebilled.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .common import read, write

MODEL = 'gemini-embedding-2'
PROJECT = 'crossword-489306'
DIMENSIONS = 768


class BudgetLedger:
    def __init__(self, path, cap=12.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY,key TEXT NOT NULL,input_sha256 TEXT NOT NULL,started REAL NOT NULL,completed REAL,reserved_usd REAL NOT NULL,status TEXT NOT NULL,http_status INTEGER,estimated_usd REAL,receipt TEXT)')
            expected = {'cap_usd': str(cap), 'model': MODEL, 'project': PROJECT, 'dimensions': str(DIMENSIONS)}
            for key, value in expected.items():
                db.execute('INSERT OR IGNORE INTO config VALUES (?,?)', (key, value))
                if db.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()[0] != value:
                    raise ValueError('Ledger configuration changed: ' + key)
        self.cap = cap

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, key, digest, amount, retry=False):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT status,input_sha256 FROM calls WHERE key=? ORDER BY id DESC', (key,)).fetchall()
            if rows:
                if any(h != digest for _, h in rows):
                    raise ValueError('Input changed for reserved key')
                if any(s in ('in_flight', 'ok') for s, _ in rows):
                    raise ValueError('Request already completed or in flight; inspect receipt')
                if not retry:
                    raise ValueError('Previous failure requires explicit retry')
            spent = db.execute('SELECT coalesce(sum(reserved_usd),0) FROM calls').fetchone()[0]
            if amount <= 0 or spent + amount > self.cap + 1e-12:
                raise ValueError('Conservative reservation cap reached')
            cursor = db.execute('INSERT INTO calls(key,input_sha256,started,reserved_usd,status) VALUES (?,?,?,?,?)',
                                (key, digest, time.time(), amount, 'in_flight'))
            return cursor.lastrowid

    def finish(self, call_id, status, http_status, cost, receipt):
        with self.connect() as db:
            if db.execute('UPDATE calls SET completed=?,status=?,http_status=?,estimated_usd=?,receipt=? WHERE id=? AND status=?',
                          (time.time(), status, http_status, cost, str(receipt), call_id, 'in_flight')).rowcount != 1:
                raise ValueError('Call already finalized')

    def totals(self):
        with self.connect() as db:
            return {'calls': db.execute('SELECT count(*) FROM calls').fetchone()[0],
                    'reserved_usd': db.execute('SELECT coalesce(sum(reserved_usd),0) FROM calls').fetchone()[0],
                    'estimated_usd': db.execute('SELECT coalesce(sum(estimated_usd),0) FROM calls').fetchone()[0],
                    'states': dict(db.execute('SELECT status,count(*) FROM calls GROUP BY status')),
                    'reservation_cap_usd': self.cap}


class BatchEmbedder:
    def __init__(self, folder, cap=12.0):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.ledger = BudgetLedger(self.folder / 'calls.sqlite', cap)
        self.auth_lock = threading.Lock()
        self.token, self.token_time = None, 0
        self.local = threading.local()

    def auth(self):
        with self.auth_lock:
            if self.token is None or time.monotonic() - self.token_time > 2400:
                sdk = Path.home() / 'AppData/Local/Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd'
                result = subprocess.run([str(sdk), 'auth', 'print-access-token'], capture_output=True, text=True, timeout=45)
                if result.returncode or not result.stdout.strip():
                    raise RuntimeError('Active Cloud SDK authentication failed')
                self.token, self.token_time = result.stdout.strip(), time.monotonic()
            return self.token

    def embed(self, key, *, image=None, text=None, retry=False):
        if (image is None) == (text is None):
            raise ValueError('Supply exactly one modality')
        if not key.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Invalid cache key')
        payload = Path(image).read_bytes() if image else text.encode('utf-8')
        source_hash = hashlib.sha256(payload).hexdigest()
        target = self.folder / (key + '.json')
        if target.exists():
            saved = read(target)
            if (saved['input_sha256'], saved['model'], saved['project'], len(saved.get('vector', []))) != (source_hash, MODEL, PROJECT, DIMENSIONS):
                raise ValueError('Cached input/model/dimensions mismatch')
            if not all(math.isfinite(x) for x in saved['vector']):
                raise ValueError('Nonfinite cached embedding')
            return saved
        token = self.auth()  # Auth failure does not reserve an API call.
        part = {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(payload).decode()}} if image else {'text': 'task: search result | query: ' + text}
        body = {'content': {'parts': [part]}, 'outputDimensionality': DIMENSIONS}
        request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        # Reservations intentionally exceed the expected 258-token image price.
        amount = 0.001 if image else max(0.0001, (len(payload) + 40) * 0.20 / 1e6)
        call_id = self.ledger.reserve(key, source_hash, amount, retry=retry)
        receipt_path = self.folder / 'receipts' / f'{call_id:06}.json'
        result = {'key': key, 'model': MODEL, 'project': PROJECT, 'dimensions': DIMENSIONS,
                  'input_sha256': source_hash, 'request_sha256': request_hash,
                  'call_id': call_id, 'modality': 'IMAGE' if image else 'TEXT', 'reserved_usd': amount}
        started = time.monotonic()
        status, http, cost = 'error', None, None
        try:
            import requests
            if not hasattr(self.local, 'session'):
                self.local.session = requests.Session()
                self.local.session.trust_env = False
            response = self.local.session.post(
                f'https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/models/{MODEL}:embedContent',
                json=body, headers={'Authorization': 'Bearer ' + token, 'x-goog-user-project': PROJECT}, timeout=90)
            http = response.status_code
            data = response.json()
            result['response'] = data
            if response.ok:
                vector = (data.get('embedding') or (data.get('embeddings') or [{}])[0]).get('values', [])
                if len(vector) != DIMENSIONS or not all(math.isfinite(x) for x in vector) or not any(vector):
                    raise ValueError('Invalid embedding in successful response')
                result['vector'] = vector
                usage = data.get('usageMetadata', {}).get('promptTokensDetails', [])
                if usage:
                    cost = sum(x['tokenCount'] * (0.45 if x['modality'] == 'IMAGE' else 0.20) / 1e6 for x in usage)
                else:
                    cost = amount
                    result['cost_is_reservation_fallback'] = True
                if cost > amount:
                    raise ValueError('Provider usage exceeds reservation; review pricing before continuing')
                status = 'ok'
            else:
                result['error'] = 'Provider HTTP ' + str(http)
        except Exception as exc:
            # Exception strings can contain request headers in some clients.
            result['error'] = type(exc).__name__
        result.update(status=status, http_status=http, estimated_usd=cost, seconds=time.monotonic()-started)
        write(receipt_path, result)
        if status == 'ok':
            write(target, result)
        self.ledger.finish(call_id, status, http, cost, receipt_path)
        if status != 'ok':
            raise RuntimeError(f'Embedding {key} failed; inspect receipt {call_id}')
        return result
