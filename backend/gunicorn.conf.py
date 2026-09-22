"""Gunicorn settings, loaded automatically from the working directory at startup.

The Dockerfile's command line sets everything else. This file only changes the log
format: with DJANGO_LOG_FORMAT=json, Gunicorn's own records (startup, workers, and the
access log) use the same JSON format as Django's, so every line of output is JSON.
Gunicorn reads the variable from its environment, before Django loads .env.
"""

import os

from config.logs import FORMATTERS

if os.environ.get("DJANGO_LOG_FORMAT") == "json":
    logconfig_dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": FORMATTERS["json"]},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            },
        },
        # Until Django configures logging in each worker, other loggers' warnings, such
        # as a failed ECS metadata lookup while the settings load, come out here. INFO
        # stays off, as without this file: in the image, django-environ reports at INFO
        # that there's no .env file, which is expected there.
        "root": {"level": "WARNING", "handlers": ["console"]},
        # No propagation: once Django configures the root logger, it has its own console
        # handler, and propagated records would print twice.
        "loggers": {
            "gunicorn.error": {"handlers": ["console"], "propagate": False},
            "gunicorn.access": {"handlers": ["console"], "propagate": False},
        },
    }
