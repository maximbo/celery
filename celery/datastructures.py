"""

Custom Datastructures

"""
import multiprocessing
from UserList import UserList


class PositionQueue(UserList):
    """A positional queue of a specific length, with slots that are either
    filled or unfilled. When all of the positions are filled, the queue
    is considered :meth:`full`.

    :param length: see :attr:`length`.


    .. attribute:: length

        The number of items required for the queue to be considered full.

    """

    class UnfilledPosition(object):
        """Describes an unfilled slot."""

        def __init__(self, position):
            self.position = position

    def __init__(self, length):
        self.length = length
        self.data = map(self.UnfilledPosition, xrange(length))

    def full(self):
        """Returns ``True`` if all of the slots has been filled."""
        return len(self) >= self.length

    def __len__(self):
        """``len(self)`` -> number of slots filled with real values."""
        return len(self.filled)

    @property
    def filled(self):
        """Returns the filled slots as a list."""
        return filter(lambda v: not isinstance(v, self.UnfilledPosition),
                      self.data)


class TaskProcessQueue(UserList):
    """Queue of running child processes, which starts waiting for the
    processes to finish when the queue limit has been reached.

    :param limit: see :attr:`limit` attribute.

    :param logger: see :attr:`logger` attribute.

    :param done_msg: see :attr:`done_msg` attribute.


    .. attribute:: limit

        The number of processes that can run simultaneously until
        we start collecting results.

    .. attribute:: logger

        The logger used to print the :attr:`done_msg`.

    .. attribute:: done_msg

        Message logged when a tasks result has been collected.
        The message is logged with loglevel :const:`logging.INFO`.

    """

    def __init__(self, limit, process_timeout=None, logger=None,
            done_msg=None):
        self.limit = limit
        self.logger = logger
        self.done_msg = done_msg
        self.process_timeout = process_timeout
        self.data = []

    def add(self, result, task_name, task_id):
        """Add a process to the queue.

        If the queue is full, it will wait for the first task to finish,
        collects its result and remove it from the queue, so it's ready
        to accept new processes.

        :param result: A :class:`multiprocessing.AsyncResult` instance, as
            returned by :meth:`multiprocessing.Pool.apply_async`.

        :param task_name: Name of the task executed.

        :param task_id: Id of the task executed.

        """

        self.data.append([result, task_name, task_id])

        if self.data and len(self.data) >= self.limit:
            self.collect()

    def collect(self):
        """Collect results from processes that are ready."""
        processes_joined = 0
        while not processes_joined:
            for process_no, process_info in enumerate(self.data):
                result, task_name, task_id = process_info
                if result.ready():
                    try:
                        self.on_ready(result, task_name, task_id)
                    except multiprocessing.TimeoutError:
                        pass
                    else:
                        del(self[i])
                        processed_join += 1

    def on_ready(self, result, task_name, task_id):
        ret_value = result.get(timeout=self.process_timeout)
        if self.done_msg and self.logger:
            self.logger_info(self.done_msg % {
                "name": task_name,
                "id": task_id,
                "return_value": ret_value})
