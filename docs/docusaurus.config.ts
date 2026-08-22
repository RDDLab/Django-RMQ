import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Django-RMQ',
  tagline: 'Django RabbitMQ Wrappers & Tools over Pika',
  favicon: 'img/favicon.svg',

  url: 'https://django-rmq.rdd-lab.com',
  baseUrl: '/',
  trailingSlash: true,
  organizationName: 'RDDLab',
  projectName: 'Django-RMQ',

  headTags: [
    {
      tagName: 'link',
      attributes: {
        rel: 'icon',
        type: 'image/svg+xml',
        href: '/img/favicon.svg',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'icon',
        type: 'image/png',
        sizes: '32x32',
        href: '/img/favicon.png',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'icon',
        type: 'image/png',
        sizes: '192x192',
        href: '/img/favicon-192x192.png',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'apple-touch-icon',
        sizes: '180x180',
        href: '/img/apple-touch-icon-180x180.png',
      },
    },
  ],

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'ru'],
    localeConfigs: {
      en: {label: 'English', htmlLang: 'en-US'},
      ru: {label: 'Русский', htmlLang: 'ru-RU'},
    },
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: 'content',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/RDDLab/Django-RMQ/tree/main/docs/',
          editLocalizedFiles: true,
          lastVersion: 'current',
          versions: {
            current: {
              label: '1.0.5',
              path: '',
            },
            '1.0.4': {
              label: '1.0.4',
              banner: 'none',
            },
          },
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
        sitemap: {
          lastmod: 'date',
          changefreq: 'weekly',
          filename: 'sitemap.xml',
        },
      } satisfies Preset.Options,
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        language: ['en', 'ru'],
        indexDocs: true,
        indexBlog: false,
        indexPages: true,
        docsDir: 'content',
        docsRouteBasePath: '/docs',
        explicitSearchResultPath: true,
      },
    ],
  ],

  plugins: [
    function i18nDevProxy() {
      return {
        name: 'i18n-dev-proxy',
        configureWebpack(_config: unknown, isServer: boolean) {
          if (
            isServer ||
            process.env.NODE_ENV === 'production' ||
            process.env.DOCUSAURUS_CURRENT_LOCALE === 'ru'
          ) {
            return {};
          }
          return {
            mergeStrategy: {'devServer.proxy': 'replace'},
            devServer: {
              proxy: [
                {
                  context: ['/ru'],
                  target: 'http://127.0.0.1:3001',
                  changeOrigin: true,
                  ws: true,
                },
              ],
            },
          };
        },
      };
    },
  ],

  themeConfig: {
    image: 'img/logo.png',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Django-RMQ',
      logo: {
        alt: 'Django-RMQ',
        src: 'img/logo.svg',
        srcDark: 'img/logo.svg',
      },
      hideOnScroll: false,
      items: [
        {
          to: '/docs/getting-started',
          label: 'Guide',
          position: 'left',
          activeBaseRegex:
            '/docs(?:/[\\d.]+)?(?!/api-reference(?:/|$)|/contrib(?:/|$))(?:/|$)',
        },
        {
          to: '/docs/api-reference',
          label: 'API Reference',
          position: 'left',
          activeBaseRegex: '/docs(?:/[\\d.]+)?/api-reference(?:/|$)',
        },
        {
          to: '/docs/contrib',
          label: 'Contributing',
          position: 'left',
          activeBaseRegex: '/docs(?:/[\\d.]+)?/contrib(?:/|$)',
        },
        {
          type: 'docsVersionDropdown',
          position: 'right',
          dropdownActiveClassDisabled: true,
        },
        {
          type: 'localeDropdown',
          position: 'right',
        },
        {
          href: 'https://github.com/RDDLab/Django-RMQ',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Guide',
          items: [
            {label: 'Getting Started', to: '/docs/getting-started'},
            {label: 'Configuration', to: '/docs/configuration'},
            {label: 'Producers', to: '/docs/producers'},
            {label: 'Consumers', to: '/docs/consumers'},
          ],
        },
        {
          title: 'Reference',
          items: [
            {label: 'API Reference', to: '/docs/api-reference'},
            {label: 'Reliability', to: '/docs/reliability'},
            {label: 'Testing', to: '/docs/testing'},
            {label: 'Contributing', to: '/docs/contrib'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: 'https://github.com/RDDLab/Django-RMQ'},
            {label: 'PyPI', href: 'https://pypi.org/project/django-rmq/'},
            {label: 'Changelog', href: 'https://github.com/RDDLab/Django-RMQ/blob/main/CHANGELOG.md'},
          ],
        },
      ],
      copyright: `MIT Licensed | Copyright © ${new Date().getFullYear()}`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'toml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
