"""
Async task definitions for AI evaluation
Prevents blocking API calls
"""
from evaluation_service.core.logger import get_logger
from evaluation_service.core.cache import get_cache

logger = get_logger()
cache = get_cache()

class TaskQueue:
    """Simple in-memory task queue (can be replaced with RQ/Celery)"""
    
    def __init__(self):
        self._tasks = []
        self._results = {}
    
    def enqueue(self, task_type: str, task_id: str, data: dict) -> str:
        """Enqueue a task"""
        task = {
            'id': task_id,
            'type': task_type,
            'data': data,
            'status': 'pending',
            'created_at': None
        }
        self._tasks.append(task)
        logger.info(f"Task enqueued: {task_type} - {task_id}", module='QUEUE')
        return task_id
    
    def get_task_status(self, task_id: str) -> dict:
        """Get task status"""
        for task in self._tasks:
            if task['id'] == task_id:
                return task
        return None
    
    def set_task_result(self, task_id: str, result: dict):
        """Set task result"""
        for task in self._tasks:
            if task['id'] == task_id:
                task['status'] = 'completed'
                task['result'] = result
                self._results[task_id] = result
                logger.info(f"Task completed: {task_id}", module='QUEUE')
                return
        logger.warning(f"Task not found: {task_id}", module='QUEUE')
    
    def set_task_error(self, task_id: str, error: str):
        """Set task error"""
        for task in self._tasks:
            if task['id'] == task_id:
                task['status'] = 'failed'
                task['error'] = error
                logger.error(f"Task failed: {task_id} - {error}", module='QUEUE')
                return

# Global task queue
_task_queue = None

def get_task_queue():
    """Get global task queue instance"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue

# Task types
TASK_WEATHER_EVALUATION = 'weather_evaluation'
TASK_NEWS_EVALUATION = 'news_evaluation'
TASK_DANGER_PREDICTION = 'danger_prediction'
TASK_CHATBOT_GENERAL = 'chatbot_general'
TASK_CHATBOT_MEDICAL = 'chatbot_medical'
