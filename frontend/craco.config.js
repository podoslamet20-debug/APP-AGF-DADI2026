// craco.config.js
const path = require("path");
const webpack = require("webpack");
require("dotenv").config();

// Check if we're actually running the craco dev server (`craco start`)
// rather than a production build (`craco build`). Relying on NODE_ENV alone
// is unreliable because it can be overridden by the environment, which would
// cause visual-edits (and its dev-only babel/webpack plugins like
// react-refresh) to leak into production bundles. Instead, inspect the
// actual CLI command being invoked.
const cracoArgs = process.argv.slice(2);
const isBuildCommand = cracoArgs.includes("build");
const isStartCommand = cracoArgs.includes("start");
const isDevServer =
  isStartCommand ||
  (!isBuildCommand && process.env.NODE_ENV !== "production");

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

function makeDevServerV5Compatible(devServerConfig) {
  const {
    https,
    onAfterSetupMiddleware,
    onBeforeSetupMiddleware,
    onListening,
    setupMiddlewares,
    ...compatibleConfig
  } = devServerConfig;

  compatibleConfig.server =
    typeof https === "object"
      ? { type: "https", options: https }
      : https
        ? "https"
        : "http";
  compatibleConfig.headers = {
    ...compatibleConfig.headers,
    "Cross-Origin-Resource-Policy": "same-origin",
  };

  if (onBeforeSetupMiddleware || setupMiddlewares) {
    compatibleConfig.setupMiddlewares = (middlewares, devServer) => {
      if (onBeforeSetupMiddleware) {
        onBeforeSetupMiddleware(devServer);
      }

      return setupMiddlewares
        ? setupMiddlewares(middlewares, devServer)
        : middlewares;
    };
  }

  compatibleConfig.onListening = (devServer) => {
    devServer.close ??= (callback) => devServer.stopCallback(callback);

    if (onListening) {
      onListening(devServer);
    }
    if (onAfterSetupMiddleware) {
      onAfterSetupMiddleware(devServer);
    }
  };

  return compatibleConfig;
}

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }

      // Explicitly exclude react-refresh from production builds. Even when
      // @emergentbase/visual-edits is skipped, react-refresh can still be
      // pulled in by react-scripts or other dependencies via some other
      // import path. To guarantee it never ends up in the production
      // bundle, mark it as an external and actively ignore/null it out at
      // the webpack level.
      if (isBuildCommand) {
        webpackConfig.externals = webpackConfig.externals || {};
        if (Array.isArray(webpackConfig.externals)) {
          webpackConfig.externals.push({
            "react-refresh": "react-refresh",
            "react-refresh/runtime": "react-refresh/runtime",
            "react-refresh/babel": "react-refresh/babel",
          });
        } else {
          webpackConfig.externals["react-refresh"] = "react-refresh";
          webpackConfig.externals["react-refresh/runtime"] = "react-refresh/runtime";
          webpackConfig.externals["react-refresh/babel"] = "react-refresh/babel";
        }

        webpackConfig.plugins = webpackConfig.plugins || [];
        webpackConfig.plugins.push(
          new webpack.IgnorePlugin({
            resourceRegExp: /^react-refresh(\/.*)?$/,
          })
        );
        webpackConfig.plugins.push(
          new webpack.NormalModuleReplacementPlugin(
            /^react-refresh(\/.*)?$/,
            path.resolve(__dirname, "scripts/react-refresh-noop.js")
          )
        );

        // Suppress any residual react-refresh related warnings that may
        // surface from other dependencies during the production build.
        webpackConfig.ignoreWarnings = [
          ...(webpackConfig.ignoreWarnings || []),
          (warning) =>
            typeof warning.message === "string" &&
            warning.message.toLowerCase().includes("react-refresh"),
        ];
      }

      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

const configureDevServer = webpackConfig.devServer;
webpackConfig.devServer = (devServerConfig) =>
  makeDevServerV5Compatible(configureDevServer(devServerConfig));

module.exports = webpackConfig;
