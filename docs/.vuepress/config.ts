import { defineUserConfig } from "vuepress";
import { hopeTheme } from "vuepress-theme-hope";
import { viteBundler } from "@vuepress/bundler-vite";

const currentYear = new Date().getFullYear();

const enSidebar_1_0_5 = [
  { text: "Home", link: "/en/1.0.5/" },
  { text: "Getting Started", link: "/en/1.0.5/getting-started.html" },
  { text: "Configuration", link: "/en/1.0.5/configuration.html" },
  { text: "Producers", link: "/en/1.0.5/producers.html" },
  { text: "Consumers", link: "/en/1.0.5/consumers.html" },
  { text: "Topology", link: "/en/1.0.5/topology.html" },
  { text: "Registries", link: "/en/1.0.5/registries.html" },
  { text: "Management Commands", link: "/en/1.0.5/management-commands.html" },
  { text: "Reliability", link: "/en/1.0.5/reliability.html" },
  { text: "Multiple Connections", link: "/en/1.0.5/multiple-connections.html" },
  { text: "Clusters", link: "/en/1.0.5/clusters.html" },
  { text: "Testing", link: "/en/1.0.5/testing.html" },
  { text: "API Reference", link: "/en/1.0.5/api-reference.html" },
  { text: "Contribution Guide", link: "/en/1.0.5/contrib.html" },
];

const enSidebar_1_0_4 = [
  { text: "Home", link: "/en/1.0.4/" },
  { text: "Getting Started", link: "/en/1.0.4/getting-started.html" },
  { text: "Configuration", link: "/en/1.0.4/configuration.html" },
  { text: "Producers", link: "/en/1.0.4/producers.html" },
  { text: "Consumers", link: "/en/1.0.4/consumers.html" },
  { text: "Topology", link: "/en/1.0.4/topology.html" },
  { text: "Registries", link: "/en/1.0.4/registries.html" },
  { text: "Management Commands", link: "/en/1.0.4/management-commands.html" },
  { text: "Reliability", link: "/en/1.0.4/reliability.html" },
  { text: "Multiple Connections", link: "/en/1.0.4/multiple-connections.html" },
  { text: "Testing", link: "/en/1.0.4/testing.html" },
  { text: "API Reference", link: "/en/1.0.4/api-reference.html" },
  { text: "Contribution Guide", link: "/en/1.0.4/contrib.html" },
];

const ruSidebar_1_0_5 = [
  { text: "Главная", link: "/ru/1.0.5/" },
  { text: "Начало работы", link: "/ru/1.0.5/getting-started.html" },
  { text: "Конфигурация", link: "/ru/1.0.5/configuration.html" },
  { text: "Продюсеры", link: "/ru/1.0.5/producers.html" },
  { text: "Потребители", link: "/ru/1.0.5/consumers.html" },
  { text: "Топология", link: "/ru/1.0.5/topology.html" },
  { text: "Реестры", link: "/ru/1.0.5/registries.html" },
  { text: "Команды управления", link: "/ru/1.0.5/management-commands.html" },
  { text: "Надёжность", link: "/ru/1.0.5/reliability.html" },
  { text: "Несколько подключений", link: "/ru/1.0.5/multiple-connections.html" },
  { text: "Кластеры", link: "/ru/1.0.5/clusters.html" },
  { text: "Тестирование", link: "/ru/1.0.5/testing.html" },
  { text: "Справочник API", link: "/ru/1.0.5/api-reference.html" },
  { text: "Руководство по участию в разработке", link: "/ru/1.0.5/contrib.html" },
];

const ruSidebar_1_0_4 = [
  { text: "Главная", link: "/ru/1.0.4/" },
  { text: "Начало работы", link: "/ru/1.0.4/getting-started.html" },
  { text: "Конфигурация", link: "/ru/1.0.4/configuration.html" },
  { text: "Продюсеры", link: "/ru/1.0.4/producers.html" },
  { text: "Потребители", link: "/ru/1.0.4/consumers.html" },
  { text: "Топология", link: "/ru/1.0.4/topology.html" },
  { text: "Реестры", link: "/ru/1.0.4/registries.html" },
  { text: "Команды управления", link: "/ru/1.0.4/management-commands.html" },
  { text: "Надёжность", link: "/ru/1.0.4/reliability.html" },
  { text: "Несколько подключений", link: "/ru/1.0.4/multiple-connections.html" },
  { text: "Тестирование", link: "/ru/1.0.4/testing.html" },
  { text: "Справочник API", link: "/ru/1.0.4/api-reference.html" },
  { text: "Руководство по участию в разработке", link: "/ru/1.0.4/contrib.html" },
];

export default defineUserConfig({
  lang: "en-US",
  title: "Django-RMQ",
  description: "Django RabbitMQ Wrappers & Tools over Pika",
  locales: {
    "/": {
      lang: "en-US",
      title: "Django-RMQ",
      description: "Django RabbitMQ Wrappers & Tools over Pika",
    },
    "/en/": {
      lang: "en-US",
      title: "Django-RMQ",
      description: "Django RabbitMQ Wrappers & Tools over Pika",
    },
    "/ru/": {
      lang: "ru-RU",
      title: "Django-RMQ",
      description: "Обёртки и инструменты RabbitMQ для Django поверх Pika",
    },
  },
  head: [
    [
      "meta",
      {
        property: "og:image",
        content: "/logo.svg",
      },
    ],
    ["link", { rel: "icon", href: "/favicon.png", type: "image/png", sizes: "32x32" }],
    ["link", { rel: "icon", href: "/favicon-192x192.png", type: "image/png", sizes: "192x192" }],
    ["link", { rel: "apple-touch-icon", href: "/apple-touch-icon-180x180.png", sizes: "180x180" }],
  ],

  bundler: viteBundler({
    viteOptions: {
      ssr: {
        noExternal: true,
      },
    },
  }),

  theme: hopeTheme({
    hostname: "https://django-rmq.rdd-lab.com",
    logo: "/logo.svg",

    repo: "RDDLab/Django-RMQ",
    docsBranch: "main",
    docsDir: "docs",

    navbarAutoHide: "none",

    pure: true,
    copyright: false,
    displayFooter: true,
    footer: `MIT Licensed | Copyright © ${currentYear}`,

    markdown: {
      tabs: true,
      mermaid: true,
    },

    plugins: {
      readingTime: false,
      copyCode: {
        showInMobile: true,
      },

      sitemap: {
        changefreq: "daily",
        sitemapFilename: "sitemap.xml",
      },
      slimsearch: {
        suggestion: true,
      },
    },

    locales: {
      "/": {
        sidebar: false,
      },
      "/en/": {
        sidebar: {
          "/en/1.0.5/": enSidebar_1_0_5,
          "/en/1.0.4/": enSidebar_1_0_4,
        },
        navbar: [
          {
            text: "Guide",
            link: "/en/1.0.5/getting-started.html",
          },
          {
            text: "API Reference",
            link: "/en/1.0.5/api-reference.html",
          },
          {
            text: "Contributing",
            link: "/en/1.0.5/contrib.html",
          },
          {
            text: "Version",
            children: [
              { text: "1.0.5 (latest)", link: "/en/1.0.5/" },
              { text: "1.0.4", link: "/en/1.0.4/" },
            ],
          },
        ],
      },
      "/ru/": {
        sidebar: {
          "/ru/1.0.5/": ruSidebar_1_0_5,
          "/ru/1.0.4/": ruSidebar_1_0_4,
        },
        navbar: [
          {
            text: "Руководство",
            link: "/ru/1.0.5/getting-started.html",
          },
          {
            text: "Справочник API",
            link: "/ru/1.0.5/api-reference.html",
          },
          {
            text: "Участие в разработке",
            link: "/ru/1.0.5/contrib.html",
          },
          {
            text: "Версия",
            children: [
              { text: "1.0.5 (актуальная)", link: "/ru/1.0.5/" },
              { text: "1.0.4", link: "/ru/1.0.4/" },
            ],
          },
        ],
      },
    },
  }),
});
