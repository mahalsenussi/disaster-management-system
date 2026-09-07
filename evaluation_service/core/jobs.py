"""In-memory async job runner for long-running evaluations.

Prevents Cloudflare/HTTP gateway timeouts (524) by acknowledging the request
immediately with a job id and executing the heavy work (slow Ollama evaluations)
in a background thread. Callers poll GET /api/jobs/<id> until the job completes.
"""

import threading
import time
import uuid
from collections import OrderedDict

JOBS: 'OrderedDict[str, dict]' = OrderedDict()
LOCK = threading.Lock()
MAX_JOBS = 100
JOB_TTL_SECONDS = 2 * 60 * 60  # 2 hours


def submit_job(fn, *args, **kwargs) -> str:
    """Run fn(args, kwargs) in a background thread, returning a job id."""
    job_id = uuid.uuid4().hex[:12]
    job = {
        'id': job_id,
        'status': 'running',
        'result': None,
        'error': None,
        'created_at': time.time(),
    }

    with LOCK:
        JOBS[job_id] = job
        cutoff = time.time() - JOB_TTL_SECONDS
        for old_id in [k for k in list(JOBS.keys()) if (JOBS[k]['created_at'] or 0) < cutoff]:
            JOBS.pop(old_id, None)
        while len(JOBS) > MAX_JOBS:
            JOBS.popitem(last=False)

    def _worker():
        try:
            job['result'] = fn(*args, **kwargs)
            job['status'] = 'success'
        except Exception as e:
            job['error'] = str(e)
            job['status'] = 'error'
        finally:
            job['finished_at'] = time.time()

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict:
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return {
            'id': job['id'],
            'status': job['status'],
            'result': job['result'],
            'error': job['error'],
            'created_at': job['created_at'],
            'finished_at': job.get('finished_at'),
        }