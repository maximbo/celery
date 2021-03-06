"""celery.views"""
from django.http import HttpResponse, Http404

from anyjson import serialize as JSON_dump

from celery.utils import get_full_cls_name
from celery.result import AsyncResult
from celery.registry import tasks
from celery.backends import default_backend


def apply(request, task_name, args):
    """View applying a task.

    Example:
        http://e.com/celery/apply/task_name/arg1/arg2//?kwarg1=a&kwarg2=b

    **NOTE** Use with caution, preferably not make this publicly accessible
    without ensuring your code is safe!

    """
    args = args.split("/")
    kwargs = request.method == "POST" and \
            request.POST.copy() or request.GET.copy()
    kwargs = dict((key.encode("utf-8"), value)
                    for key, value in kwargs.items())
    if task_name not in tasks:
        raise Http404("apply: no such task")

    task = tasks[task_name]
    result = task.apply_async(args=args, kwargs=kwargs)
    response_data = {"ok": "true", "task_id": result.task_id}
    return HttpResponse(JSON_dump(response_data), mimetype="application/json")


def is_task_successful(request, task_id):
    """Returns task execute status in JSON format."""
    response_data = {"task": {"id": task_id,
                              "executed": AsyncResult(task_id).successful()}}
    return HttpResponse(JSON_dump(response_data), mimetype="application/json")
is_task_done = is_task_successful # Backward compatible


def task_status(request, task_id):
    """Returns task status and result in JSON format."""
    status = default_backend.get_status(task_id)
    res = default_backend.get_result(task_id)
    response_data = dict(id=task_id, status=status, result=res)
    if status in default_backend.EXCEPTION_STATES:
        traceback = default_backend.get_traceback(task_id)
        response_data.update({"result": str(res.args[0]),
                              "exc": get_full_cls_name(res.__class__),
                              "traceback": traceback})

    return HttpResponse(JSON_dump({"task": response_data}),
            mimetype="application/json")
