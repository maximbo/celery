from datetime import datetime, timedelta

from celery import conf
from celery.utils import gen_unique_id, fun_takes_kwargs, mattrgetter
from celery.result import EagerResult
from celery.execute.trace import TaskTrace
from celery.registry import tasks
from celery.messaging import with_connection

extract_exec_options = mattrgetter("routing_key", "exchange",
                                   "immediate", "mandatory",
                                   "priority", "serializer")


def apply_async(task, args=None, kwargs=None, countdown=None, eta=None,
        task_id=None, publisher=None, connection=None, connect_timeout=None,
        **options):
    """Run a task asynchronously by the celery daemon(s).

    :param task: The task to run (a callable object, or a :class:`Task`
        instance

    :keyword args: The positional arguments to pass on to the
        task (a ``list``).

    :keyword kwargs: The keyword arguments to pass on to the task (a ``dict``)

    :keyword countdown: Number of seconds into the future that the task should
        execute. Defaults to immediate delivery (Do not confuse that with
        the ``immediate`` setting, they are unrelated).

    :keyword eta: A :class:`datetime.datetime` object that describes the
        absolute time when the task should execute. May not be specified
        if ``countdown`` is also supplied. (Do not confuse this with the
        ``immediate`` setting, they are unrelated).

    :keyword routing_key: The routing key used to route the task to a worker
        server.

    :keyword exchange: The named exchange to send the task to. Defaults to
        :attr:`celery.task.base.Task.exchange`.

    :keyword immediate: Request immediate delivery. Will raise an exception
        if the task cannot be routed to a worker immediately.
        (Do not confuse this parameter with the ``countdown`` and ``eta``
        settings, as they are unrelated).

    :keyword mandatory: Mandatory routing. Raises an exception if there's
        no running workers able to take on this task.

    :keyword connection: Re-use existing AMQP connection.
        The ``connect_timeout`` argument is not respected if this is set.

    :keyword connect_timeout: The timeout in seconds, before we give up
        on establishing a connection to the AMQP server.

    :keyword priority: The task priority, a number between ``0`` and ``9``.

    :keyword serializer: A string identifying the default serialization
        method to use. Defaults to the ``CELERY_TASK_SERIALIZER`` setting.
        Can be ``pickle`` ``json``, ``yaml``, or any custom serialization
        methods that have been registered with
        :mod:`carrot.serialization.registry`.

    **Note**: If the ``CELERY_ALWAYS_EAGER`` setting is set, it will be
    replaced by a local :func:`apply` call instead.

    """
    if conf.ALWAYS_EAGER:
        return apply(task, args, kwargs)
    return _apply_async(task, args=args, kwargs=kwargs, countdown=countdown,
                        eta=eta, task_id=task_id, publisher=publisher,
                        connection=connection,
                        connect_timeout=connect_timeout, **options)


@with_connection
def _apply_async(task, args=None, kwargs=None, countdown=None, eta=None,
        task_id=None, publisher=None, connection=None, connect_timeout=None,
        **options):

    task = tasks[task.name] # Get instance.
    exchange = options.get("exchange")
    options = dict(extract_exec_options(task), **options)

    if countdown: # Convert countdown to ETA.
        eta = datetime.now() + timedelta(seconds=countdown)

    publish = publisher or task.get_publisher(connection, exchange=exchange)
    try:
        task_id = publish.delay_task(task.name, args or [], kwargs or {},
                                     task_id=task_id,
                                     eta=eta,
                                     **options)
    finally:
        publisher or publish.close()

    return task.AsyncResult(task_id)


def delay_task(task_name, *args, **kwargs):
    """Delay a task for execution by the ``celery`` daemon.

    :param task_name: the name of a task registered in the task registry.
    :param \*args: positional arguments to pass on to the task.
    :param \*\*kwargs: keyword arguments to pass on to the task.

    :raises celery.exceptions.NotRegistered: exception if no such task
        has been registered in the task registry.

    :returns: :class:`celery.result.AsyncResult`.

    Example

        >>> r = delay_task("update_record", name="George Constanza", age=32)
        >>> r.ready()
        True
        >>> r.result
        "Record was updated"

    """
    return apply_async(tasks[task_name], args, kwargs)


def apply(task, args, kwargs, **options):
    """Apply the task locally.

    This will block until the task completes, and returns a
    :class:`celery.result.EagerResult` instance.

    """
    args = args or []
    kwargs = kwargs or {}
    task_id = gen_unique_id()
    retries = options.get("retries", 0)

    task = tasks[task.name] # Make sure we get the instance, not class.

    default_kwargs = {"task_name": task.name,
                      "task_id": task_id,
                      "task_retries": retries,
                      "task_is_eager": True,
                      "logfile": None,
                      "loglevel": 0}
    supported_keys = fun_takes_kwargs(task.run, default_kwargs)
    extend_with = dict((key, val) for key, val in default_kwargs.items()
                            if key in supported_keys)
    kwargs.update(extend_with)

    trace = TaskTrace(task.name, task_id, args, kwargs, task=task)
    retval = trace.execute()
    return EagerResult(task_id, retval, trace.status, traceback=trace.strtb)
