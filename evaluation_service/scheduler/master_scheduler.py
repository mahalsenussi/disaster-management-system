"""
Central scheduler for unified control of all collection schedules
Prevents drift and overlapping issues
"""
import time
import threading
import schedule
from datetime import datetime
from typing import Callable, Dict
from evaluation_service.core.logger import get_logger

logger = get_logger()

class MasterScheduler:
    """Central scheduler for all collection tasks"""
    
    def __init__(self):
        self._running = False
        self._thread = None
        self._jobs: Dict[str, schedule.Job] = {}
    
    def add_job(self, job_id: str, func: Callable, interval_minutes: int, at_time: str = None):
        """Add a scheduled job
        
        Args:
            job_id: Unique identifier for the job
            func: Function to execute
            interval_minutes: Interval in minutes
            at_time: Specific time to run (e.g., "00:00", "00:20", "00:40")
        """
        if at_time:
            # Schedule at specific time every hour
            job = schedule.every().hour.at(at_time).do(func)
        else:
            # Schedule at interval
            job = schedule.every(interval_minutes).minutes.do(func)
        
        self._jobs[job_id] = job
        logger.info(f"Job scheduled: {job_id} - Every {interval_minutes}min at {at_time}", module='SCHEDULER')
    
    def remove_job(self, job_id: str):
        """Remove a scheduled job"""
        if job_id in self._jobs:
            schedule.cancel_job(self._jobs[job_id])
            del self._jobs[job_id]
            logger.info(f"Job removed: {job_id}", module='SCHEDULER')
    
    def start(self):
        """Start the scheduler thread"""
        if self._running:
            logger.warning("Scheduler already running", module='SCHEDULER')
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started", module='SCHEDULER')
    
    def stop(self):
        """Stop the scheduler thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped", module='SCHEDULER')
    
    def _run_loop(self):
        """Main scheduler loop"""
        while self._running:
            schedule.run_pending()
            time.sleep(1)
    
    def get_jobs(self) -> Dict[str, str]:
        """Get all scheduled jobs with their next run time"""
        jobs_info = {}
        for job_id, job in self._jobs.items():
            next_run = job.next_run
            if next_run:
                jobs_info[job_id] = next_run.isoformat()
            else:
                jobs_info[job_id] = "Not scheduled"
        return jobs_info

# Global scheduler instance
_scheduler = None

def get_scheduler():
    """Get global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = MasterScheduler()
    return _scheduler
