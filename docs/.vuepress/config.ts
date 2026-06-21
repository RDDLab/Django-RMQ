import { defineUserConfig } from "vuepress";
import { hopeTheme } from "vuepress-theme-hope";
import { viteBundler } from "@vuepress/bundler-vite";

const currentYear = new Date().getFullYear();

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
        sidebar: [
          {
            text: "Django-RMQ General",
            link: "/en/",
          },
          {
            text: "Contribution guide",
            link: "/en/contrib.html",
          },
        ],
        navbar: [
          {
            text: "Contributing",
            link: "/en/contrib.html",
          },
        ],
      },
    },
  }),
});
