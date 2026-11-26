FROM node:24.22.3-bookworm-slim AS dependencies
WORKDIR /docs
COPY docs/package.json docs/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm install --global "$(node -p 'require("./package.json").packageManager')"
RUN --mount=type=cache,target=/root/.npm npm ci

FROM dependencies AS site-build
COPY docs/ ./
RUN DOCS_WITHOUT_GIT=1 npm run docs:build
RUN test -s build/index.html && test -s build/ru/index.html

FROM docker.angie.software/angie:1.12.5-minimal AS runtime
COPY .github/docs/angie.conf /etc/angie/angie.conf
COPY --from=site-build /docs/build/ /usr/share/angie/html/
USER angie
EXPOSE 8080
STOPSIGNAL SIGQUIT
ENTRYPOINT ["angie"]
CMD ["-g", "daemon off;"]
