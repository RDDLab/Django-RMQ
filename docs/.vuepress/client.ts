import { defineClientConfig, resolveRoute } from "vuepress/client";

// Matches paths like "/en/1.0.5/producers.html" ->
//   [1] locale ("en" | "ru"), [2] version ("1.0.5"), [3] rest ("producers.html")
const VERSION_RE = /^\/(en|ru)\/(\d+\.\d+\.\d+)\/(.*)$/;

export default defineClientConfig({
  enhance({ router }) {
    // Keep the reader on the same page when they switch docs versions.
    // The navbar "Version" links are static and point to the version root
    // (e.g. /en/1.0.4/), so vue-router would otherwise drop the current page.
    router.beforeEach((to, from) => {
      const toMatch = to.path.match(VERSION_RE);
      const fromMatch = from.path.match(VERSION_RE);
      if (!toMatch || !fromMatch) {
        return;
      }

      const [, toLocale, toVersion, toRest] = toMatch;
      const [, fromLocale, fromVersion, fromRest] = fromMatch;

      // Only rewrite an actual version switch inside the same locale, when the
      // target is a version root and we are currently on a real sub-page.
      if (toLocale !== fromLocale) {
        return;
      }
      if (toVersion === fromVersion) {
        return;
      }
      if (toRest !== "") {
        return;
      }
      if (fromRest === "") {
        return;
      }

      // Stay on the equivalent page in the target version, if it exists.
      const candidate = `/${toLocale}/${toVersion}/${fromRest}`;
      if (resolveRoute(candidate).notFound) {
        return;
      }

      return candidate;
    });
  },
});
