import {useState, type ReactNode} from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import {useLatestVersion} from '@docusaurus/plugin-content-docs/client';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

type Copy = {
  title: string;
  description: string;
  kicker: string;
  heroTitle: string;
  lead: string;
  getStarted: string;
  api: string;
  github: string;
  install: string;
  copyInstall: string;
  copiedInstall: string;
  howTitle: string;
  steps: {title: string; body: string}[];
  featuresTitle: string;
  features: {title: string; body: string}[];
  guidesTitle: string;
  guides: {title: string; body: string; to: string}[];
};

const en: Copy = {
  title: 'Django-RMQ',
  description: 'Django RabbitMQ wrappers and tools over Pika',
  kicker: 'Django RabbitMQ wrappers over Pika',
  heroTitle: 'Predictable messaging for Django',
  lead: 'Publish and consume RabbitMQ messages from a Django project without turning it into a task queue. Thin Pika wrappers, native settings, and infrastructure code that stays close to your app.',
  getStarted: 'Get started',
  api: 'API reference',
  github: 'GitHub',
  install: 'pip install django-rmq',
  copyInstall: 'Copy',
  copiedInstall: 'Copied',
  howTitle: 'From install to a running consumer',
  steps: [
    {
      title: 'Install the package',
      body: 'Add django-rmq, then register it in INSTALLED_APPS.',
    },
    {
      title: 'Configure the broker',
      body: 'Declare RABBITMQ_CONNECTIONS in settings.py — one alias per connection.',
    },
    {
      title: 'Publish or consume',
      body: 'Use Producer and Consumer wrappers instead of spreading Pika boilerplate.',
    },
  ],
  featuresTitle: 'Why Django-RMQ',
  features: [
    {
      title: 'Production ready',
      body: 'Built for Django projects that need predictable RabbitMQ integration in real applications.',
    },
    {
      title: 'Django native',
      body: 'Keep connection settings and messaging code next to the rest of your Django configuration.',
    },
    {
      title: 'Easily extensible',
      body: 'Small wrappers for producers and consumers, not a framework that takes over the app.',
    },
    {
      title: 'Strongly typed',
      body: 'Typing support so editors and type checkers can help while you work with messaging code.',
    },
  ],
  guidesTitle: 'Guides',
  guides: [
    {title: 'Configuration', body: 'RABBITMQ_CONNECTIONS and broker aliases.', to: '/docs/configuration'},
    {title: 'Producers', body: 'Publish, decorator mode, confirms.', to: '/docs/producers'},
    {title: 'Consumers', body: 'Handlers, ack/nack, reconnect backoff.', to: '/docs/consumers'},
    {title: 'Topology', body: 'QueueConfig, setup functions, DLX.', to: '/docs/topology'},
    {title: 'Reliability', body: 'At-least-once delivery and self-heal.', to: '/docs/reliability'},
    {title: 'Clusters', body: 'Multi-node failover with NODES.', to: '/docs/clusters'},
  ],
};

const ru: Copy = {
  title: 'Django-RMQ',
  description: 'Обёртки и инструменты RabbitMQ для Django поверх Pika',
  kicker: 'Обёртки RabbitMQ для Django поверх Pika',
  heroTitle: 'Предсказуемый обмен сообщениями для Django',
  lead: 'Публикуйте и потребляйте сообщения RabbitMQ из Django-проекта, не превращая его в очередь задач. Тонкие обёртки над Pika, нативные настройки и инфраструктурный код рядом с приложением.',
  getStarted: 'Начало работы',
  api: 'Справочник API',
  github: 'GitHub',
  install: 'pip install django-rmq',
  copyInstall: 'Копировать',
  copiedInstall: 'Скопировано',
  howTitle: 'От установки до работающего потребителя',
  steps: [
    {
      title: 'Установите пакет',
      body: 'Добавьте django-rmq и зарегистрируйте его в INSTALLED_APPS.',
    },
    {
      title: 'Настройте брокер',
      body: 'Опишите RABBITMQ_CONNECTIONS в settings.py — один alias на подключение.',
    },
    {
      title: 'Публикуйте или потребляйте',
      body: 'Используйте обёртки Producer и Consumer вместо boilerplate-кода Pika.',
    },
  ],
  featuresTitle: 'Почему Django-RMQ',
  features: [
    {
      title: 'Готов к продакшену',
      body: 'Для Django-проектов, которым нужна предсказуемая интеграция с RabbitMQ в реальных приложениях.',
    },
    {
      title: 'Нативная интеграция с Django',
      body: 'Настройки подключения и код обмена сообщениями рядом с конфигурацией проекта.',
    },
    {
      title: 'Легко расширяется',
      body: 'Небольшие обёртки для продюсеров и консьюмеров, а не фреймворк, который захватывает приложение.',
    },
    {
      title: 'Строгая типизация',
      body: 'Поддержка типов, чтобы редакторы и type checker помогали при работе с messaging-кодом.',
    },
  ],
  guidesTitle: 'Руководства',
  guides: [
    {title: 'Конфигурация', body: 'RABBITMQ_CONNECTIONS и alias брокера.', to: '/docs/configuration'},
    {title: 'Продюсеры', body: 'Публикация, декоратор, confirms.', to: '/docs/producers'},
    {title: 'Потребители', body: 'Обработчики, ack/nack, reconnect.', to: '/docs/consumers'},
    {title: 'Топология', body: 'QueueConfig, setup-функции, DLX.', to: '/docs/topology'},
    {title: 'Надёжность', body: 'Доставка at-least-once и self-heal.', to: '/docs/reliability'},
    {title: 'Кластеры', body: 'Failover по нескольким нодам через NODES.', to: '/docs/clusters'},
  ],
};

function versionBadge(label: string): string {
  return label.startsWith('v') ? label : `v${label}`;
}

function InstallCommand({
  command,
  copyLabel,
  copiedLabel,
}: {
  command: string;
  copyLabel: string;
  copiedLabel: string;
}): ReactNode {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className={styles.install}>
      <code>{command}</code>
      <button type="button" className={styles.installCopy} onClick={copy} aria-label={copyLabel}>
        {copied ? copiedLabel : copyLabel}
      </button>
    </div>
  );
}

export default function Home(): ReactNode {
  const {i18n} = useDocusaurusContext();
  const copy = i18n.currentLocale === 'ru' ? ru : en;
  const logoSrc = useBaseUrl('/img/logo.svg');
  const latestVersion = useLatestVersion(undefined);

  return (
    <Layout title={copy.title} description={copy.description}>
      <header className={styles.hero}>
        <div className="container">
          <div className={styles.heroInner}>
            <img
              className={styles.heroMark}
              src={logoSrc}
              alt="Django-RMQ"
              width={380}
              height={68}
            />
            <p className={styles.kicker}>
              {copy.kicker}
              <span className={styles.version}>{versionBadge(latestVersion.label)}</span>
            </p>
            <Heading as="h1" className={styles.heroTitle}>
              {copy.heroTitle}
            </Heading>
            <p className={styles.heroLead}>{copy.lead}</p>
            <div className={styles.actions}>
              <Link className="button button--primary button--lg" to="/docs/getting-started">
                {copy.getStarted}
              </Link>
              <Link className="button button--secondary button--lg" to="/docs/api-reference">
                {copy.api}
              </Link>
              <Link
                className="button button--secondary button--lg"
                to="https://github.com/RDDLab/Django-RMQ"
              >
                {copy.github}
              </Link>
            </div>
            <InstallCommand
              command={copy.install}
              copyLabel={copy.copyInstall}
              copiedLabel={copy.copiedInstall}
            />
          </div>
        </div>
      </header>

      <main>
        <section className={styles.section}>
          <div className="container">
            <Heading as="h2" className={styles.sectionTitle}>
              {copy.howTitle}
            </Heading>
            <div className={styles.grid3}>
              {copy.steps.map((step, index) => (
                <article className={styles.card} key={step.title}>
                  <span className={styles.step}>{String(index + 1).padStart(2, '0')}</span>
                  <Heading as="h3">{step.title}</Heading>
                  <p>{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className="container">
            <Heading as="h2" className={styles.sectionTitle}>
              {copy.featuresTitle}
            </Heading>
            <div className={styles.grid4}>
              {copy.features.map((feature) => (
                <article className={styles.card} key={feature.title}>
                  <Heading as="h3">{feature.title}</Heading>
                  <p>{feature.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className="container">
            <Heading as="h2" className={styles.sectionTitle}>
              {copy.guidesTitle}
            </Heading>
            <div className={styles.guides}>
              {copy.guides.map((guide) => (
                <Link className={styles.guide} key={guide.to} to={guide.to}>
                  <Heading as="h3">{guide.title}</Heading>
                  <p>{guide.body}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
