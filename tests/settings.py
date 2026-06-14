"""
Minimal Django settings used to run the django_rmq test suite.
"""

from typing import Any

SECRET_KEY: str = 'django-rmq-test-secret-key'

USE_TZ: bool = True

INSTALLED_APPS: list[str] = [
    'django_rmq',
]

DATABASES: dict[str, dict[str, Any]] = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

# Default single-alias broker fixture. Hostname/credentials are never dialed in
# unit tests — pika is mocked — they only feed RabbitMQConfig construction.
RABBITMQ_CONNECTIONS: dict[str, dict[str, Any]] = {
    'default': {
        'HOST': 'localhost',
        'PORT': 5672,
        'VIRTUAL_HOST': '/',
        'USER': 'guest',
        'PASSWORD': 'guest',
        'HEARTBEAT': 600,
        'BLOCKED_CONNECTION_TIMEOUT': 300,
        'RECONNECT_INITIAL_BACKOFF': 1.0,
        'RECONNECT_MAX_BACKOFF': 30.0,
    },
}
