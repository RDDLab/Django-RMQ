import { defineUserConfig } from "vuepress";
import { hopeTheme } from "vuepress-theme-hope";
import { viteBundler } from "@vuepress/bundler-vite";

const currentYear = new Date().getFullYear();

const enSidebar = [
  { text: "Home", link: "/en/" },
  { text: "Getting Started", link: "/en/getting-started.html" },
  { text: "Configuration", link: "/en/configuration.html" },
  { text: "Producers", link: "/en/producers.html" },
  { text: "Consumers", link: "/en/consumers.html" },
  { text: "Topology", link: "/en/topology.html" },
  { text: "Registries", link: "/en/registries.html" },
  { text: "Management Commands", link: "/en/management-commands.html" },
  { text: "Reliability", link: "/en/reliability.html" },
  { text: "Multiple Connections", link: "/en/multiple-connections.html" },
  { text: "Testing", link: "/en/testing.html" },
  { text: "API Reference", link: "/en/api-reference.html" },
  { text: "Contribution Guide", link: "/en/contrib.html" },
];

const ruSidebar = [
  { text: "Главная", link: "/ru/" },
  { text: "Начало работы", link: "/ru/getting-started.html" },
  { text: "Конфигурация", link: "/ru/configuration.html" },
  { text: "Продюсеры", link: "/ru/producers.html" },
  { text: "Потребители", link: "/ru/consumers.html" },
  { text: "Топология", link: "/ru/topology.html" },
  { text: "Реестры", link: "/ru/registries.html" },
  { text: "Команды управления", link: "/ru/management-commands.html" },
  { text: "Надёжность", link: "/ru/reliability.html" },
  { text: "Несколько подключений", link: "/ru/multiple-connections.html" },
  { text: "Тестирование", link: "/ru/testing.html" },
  { text: "Справочник API", link: "/ru/api-reference.html" },
  { text: "Руководство по участию в разработке", link: "/ru/contrib.html" },
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
        sidebar: enSidebar,
        navbar: [
          {
            text: "Guide",
            link: "/en/getting-started.html",
          },
          {
            text: "API Reference",
            link: "/en/api-reference.html",
          },
          {
            text: "Contributing",
            link: "/en/contrib.html",
          },
        ],
      },
      "/ru/": {
        sidebar: ruSidebar,
        navbar: [
          {
            text: "Руководство",
            link: "/ru/getting-started.html",
          },
          {
            text: "Справочник API",
            link: "/ru/api-reference.html",
          },
          {
            text: "Участие в разработке",
            link: "/ru/contrib.html",
          },
        ],
      },
    },
  }),
});
