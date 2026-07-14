---
title: Django-RMQ Общее
home: true
heroImage: /logo.svg
heroAlt: Django-RMQ
heroText: false
tagline: Обёртки и инструменты для RabbitMQ в Django на базе Pika
actions:
  - text: Начало работы
    link: /ru/1.0.4/getting-started.html
    type: primary
  - text: Введение
    link: /ru/1.0.4/#what-is-django-rmq-in-a-nutshell
    type: secondary
highlights:
  - features:
      - title: Готов к продакшену
        details: Django-RMQ создан для Django-проектов, которым нужна предсказуемая интеграция с RabbitMQ в реальных приложениях.
      - title: Нативная интеграция с Django
        details: Настройки подключения к RabbitMQ и код обмена сообщениями находятся рядом с конфигурацией Django-проекта.
      - title: Легко расширяется
        details: Строите продюсеров и консьюмеров поверх небольших обёрток вместо того, чтобы разбрасывать boilerplate-код Pika по всей кодовой базе.
      - title: Строгая типизация
        details: Django-RMQ поставляется с поддержкой типов, так что редакторы и type-checker'ы помогают при работе с кодом обмена сообщениями.
---

## Что такое Django-RMQ в двух словах

Django-RMQ предоставляет обёртки и инструменты для работы с RabbitMQ в Django-проектах через Pika.

Это не полноценная очередь задач и не замена Celery. Это лёгкий интеграционный слой для проектов, которым нужно
публиковать сообщения, потреблять сообщения и держать инфраструктурный код RabbitMQ в порядке внутри Django-приложения.

## Обзор возможностей

- [Конфигурация](/ru/1.0.4/configuration.html) — `RABBITMQ_CONNECTIONS` в `settings.py`; одна запись на каждый alias брокера.
- [Продюсеры](/ru/1.0.4/producers.html) — публикация сообщений, режим декоратора, персистентная доставка, publisher confirms.
- [Консьюмеры](/ru/1.0.4/consumers.html) — регистрация обработчиков, явный ack/nack, экспоненциальная задержка
  переподключения.
- [Топология](/ru/1.0.4/topology.html) — `QueueConfig`, функции настройки, dead-letter routing.
- [Реестры](/ru/1.0.4/registries.html) — `ConsumersRegistry` и `SetupRegistry` для каждого alias.
- [Management-команды](/ru/1.0.4/management-commands.html) — `setup_rabbitmq_topology` и `start_consumers`.
- [Надёжность](/ru/1.0.4/reliability.html) — доставка at-least-once, mandatory routing, самовосстановление продюсера, DLX.
- [Несколько подключений](/ru/1.0.4/multiple-connections.html) — несколько alias'ов брокера через параметр `using=`.
- [Справочник API](/ru/1.0.4/api-reference.html) — полные сигнатуры и описание параметров для каждого публичного символа.
- [Тестирование](/ru/1.0.4/testing.html) — юнит-тесты с замоканным Pika; интеграционные тесты с реальным брокером.

## Установка

Установите пакет:

```bash
pip install django-rmq
```

Добавьте `'django_rmq'` в `INSTALLED_APPS` и добавьте блок `RABBITMQ_CONNECTIONS` в `settings.py`. Смотрите
руководство [Начало работы](/ru/1.0.4/getting-started.html) для минимальной конфигурации.

## Тестирование

Смотрите страницу [Тестирование](/ru/1.0.4/testing.html) для инструкций по запуску юнит- и интеграционных тестов.
