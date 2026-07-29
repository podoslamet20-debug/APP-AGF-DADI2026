# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder stage
#
# This is the ONLY stage where react-scripts / craco / babel / react-refresh
# are present. CI=true, NODE_ENV=production and DISABLE_ESLINT_PLUGIN=true
# are set explicitly (rather than relying on Nixpacks auto-detection) so
# the CRA/webpack config always takes the production branch and never wires
# up react-refresh or any other dev-only/HMR tooling.
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first so this layer is cached when only source
# files change.
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# Copy the rest of the source and build the production bundle.
COPY . .

ENV CI=true
ENV NODE_ENV=production
ENV DISABLE_ESLINT_PLUGIN=true
ENV GENERATE_SOURCEMAP=false

RUN yarn run build

# ---------------------------------------------------------------------------
# Runtime stage
#
# Only the static build output is copied into this stage. There is no
# node_modules, no source code and no react-scripts here, so react-refresh
# (or any other dev dependency) can never be shipped to the browser.
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS runtime

WORKDIR /app

# `serve` is a tiny, production-grade static file server. It is the only
# runtime dependency in this image.
RUN npm install --global serve@14

COPY --from=builder /app/build ./build

EXPOSE 3000

CMD ["serve", "-s", "build", "-l", "3000"]
