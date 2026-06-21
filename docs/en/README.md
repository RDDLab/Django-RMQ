---
title: Django-RMQ General
home: true
heroImage: /logo.svg
heroAlt: Django-RMQ
heroText: false
tagline: Django RabbitMQ Wrappers & Tools over Pika
actions:
  - text: Get Started
    link: /en/#installation
    type: primary
  - text: Introduction
    link: /en/#what-is-django-rmq-in-a-nutshell
    type: secondary
highlights:
  - features:
      - title: Production ready
        details: Django-RMQ is designed for Django projects that need predictable RabbitMQ integration in real applications.
      - title: Django native
        details: Keep RabbitMQ connection settings and messaging code close to your Django project configuration.
      - title: Easily extensible
        details: Build producers and consumers around small wrappers instead of spreading Pika boilerplate across the codebase.
      - title: Strongly typed
        details: Django-RMQ ships typing support, so editors and type checkers can help while you work with messaging code.
---

## What is Django-RMQ in a nutshell

Django-RMQ provides RabbitMQ wrappers and tools for Django projects using Pika.

It is not a full task queue or a Celery replacement. It is a lightweight integration layer for projects that want to publish messages, consume messages, and keep RabbitMQ infrastructure code tidy inside a Django application.

## Installation

You can install Django-RMQ with pip or your favorite Python dependency manager:

```bash
pip install django-rmq
```
