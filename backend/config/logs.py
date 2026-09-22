"""Log formats for Django (settings.py) and Gunicorn (gunicorn.conf.py).

DJANGO_LOG_FORMAT picks one. "plain", the default, is easy to read in a terminal. "json"
writes one JSON object per line, which CloudWatch Logs Insights can query field by field,
and which keeps a traceback inside its record instead of spreading it over many lines.
"""

FORMATTERS = {
    "plain": {
        "format": "{asctime} {levelname} {name} {message}",
        "style": "{",
    },
    "json": {
        "()": "pythonjsonlogger.json.JsonFormatter",
        "fmt": ["levelname", "name", "message"],
        "rename_fields": {"levelname": "level", "name": "logger"},
        "timestamp": "time",
    },
}
