import time
import shelve
import atexit
import threading
from UserDict import UserDict
from datetime import datetime
from celery import conf
from celery import registry
from celery.log import setup_logger



class SchedulingError(Exception):
    """An error occured while scheduling task."""


class ScheduleEntry(object):
    """An entry in the scheduler.

    :param task: The task class.
    :keyword last_run_at: The time and date when this task was last run.
    :keyword total_run_count: Total number of times this periodic task has
        been executed.

    """

    def __init__(self, task, last_run_at=None, total_run_count=None):
        self.task = task
        self.last_run_at = last_run_at or datetime.now()
        self.total_run_count = total_run_count or 0

    def execute(self):
        # Increment timestamps and counts before executing,
        # in case of exception.
        self.last_run_at = datetime.now()
        self.total_run_count += 1

        try:
            result = self.task.apply_async()
        except Exception, exc:
            raise SchedulingError(
                    "Couldn't apply scheduled task %s: %s" % (
                        self.task.name, exc))
        return result

    def is_due(self):
        return datetime.now() > (self.last_run_at + self.task.run_every)


class Scheduler(UserDict):
    """Scheduler for periodic tasks.

    :keyword registry: The task registry to use.
    :keyword schedule: The schedule dictionary. Default is the global
        persistent schedule ``celery.beat.schedule``.

    """
    interval = 1

    def __init__(self, registry=None, schedule=None, interval=None,
            logger=None):
        self.registry = registry or {}
        self.data = schedule or {}
        if interval is not None:
            self.interval = interval
        self.schedule_registry()

    def tick(self):
        """Run a tick, that is one iteration of the scheduler.
        Executes all due tasks."""
        return [(entry.task, entry.execute())
                    for entry in self.get_due_tasks()]

    def get_due_tasks(self):
        """Get all the schedule entries that are due to execution."""
        return filter(lambda entry: entry.is_due(), self.schedule.values())

    def schedule_registry(self):
        """Add the current contents of the registry to the schedule."""
        periodic_tasks = self.registry.get_all_periodic()
        for name, task in self.registry.get_all_periodic().items():
            self.schedule.setdefault(name, ScheduleEntry(task))

    @property
    def schedule(self):
        return self.data


class ClockService(object):
    scheduler_cls = Scheduler
    schedule_filename = conf.CELERYBEAT_SCHEDULE_FILENAME
    registry = registry.tasks

    def __init__(self, loglevel, logfile, is_detached=False):
        self.logger = setup_logger(loglevel, logfile)
        self._shutdown = threading.Event()
        self._stopped = threading.Event()

    def start(self):
        schedule = shelve.open(filename=self.schedule_filename)
        atexit.register(schedule.close)
        scheduler = self.scheduler_cls(schedule=schedule,
                                       registry=self.registry)

        try:
            while True:
                if self._shutdown.isSet():
                    break
                scheduler.tick()
                time.sleep(scheduler.interval)
        finally:
            schedule.close()
            self._stopped.set()

    def stop(self, wait=False):
        self._shutdown.set()
        wait and self._stopped.wait() # block until shutdown done.


class ClockServiceThread(threading.Thread):

    def __init__(self, *args, **kwargs):
        self.clockservice = ClockService(*args, **kwargs)
        self.setDaemon(True)

    def run(self):
        self.clockservice.start()

    def stop(self):
        self.clockservice.stop(wait=True)
