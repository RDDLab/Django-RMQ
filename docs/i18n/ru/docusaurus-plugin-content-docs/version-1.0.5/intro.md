---
title: Django-RMQ Общее
sidebar_label: Главная
slug: /
sidebar_position: 1
---

## Что такое Django-RMQ в двух словах

Django-RMQ предоставляет обёртки и инструменты для работы с RabbitMQ в Django-проектах через Pika.

Это не полноценная очередь задач и не замена Celery. Это лёгкий интеграционный слой для проектов, которым нужно
публиковать сообщения, потреблять сообщения и держать инфраструктурный код RabbitMQ в порядке внутри Django-приложения.

## Обзор возможностей

- [Конфигурация](./configuration.md) — `RABBITMQ_CONNECTIONS` в `settings.py`; одна запись на каждый alias брокера.
- [Продюсеры](./producers.md) — публикация сообщений, режим декоратора, персистентная доставка, publisher confirms.
- [Консьюмеры](./consumers.md) — регистрация обработчиков, явный ack/nack, экспоненциальная задержка
  переподключения.
- [Топология](./topology.md) — `QueueConfig`, функции настройки, dead-letter routing.
- [Реестры](./registries.md) — `ConsumersRegistry` и `SetupRegistry` для каждого alias.
- [Management-команды](./management-commands.md) — `setup_rabbitmq_topology` и `start_consumers`.
- [Надёжность](./reliability.md) — доставка at-least-once, mandatory routing, самовосстановление продюсера, DLX.
- [Несколько подключений](./multiple-connections.md) — несколько alias'ов брокера через параметр `using=`.
- [Справочник API](./api-reference.md) — полные сигнатуры и описание параметров для каждого публичного символа.
- [Тестирование](./testing.md) — юнит-тесты с замоканным Pika; интеграционные тесты с реальным брокером.

## Установка

Установите пакет:

```bash
pip install django-rmq
```

Добавьте `'django_rmq'` в `INSTALLED_APPS` и добавьте блок `RABBITMQ_CONNECTIONS` в `settings.py`. Смотрите
руководство [Начало работы](./getting-started.md) для минимальной конфигурации.

## Тестирование

Смотрите страницу [Тестирование](./testing.md) для инструкций по запуску юнит- и интеграционных тестов.
