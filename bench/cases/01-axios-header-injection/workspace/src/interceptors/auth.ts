import type { AxiosInstance } from "axios";
import { getCurrentRequestContext } from "../context";
import { logger } from "../logger";

interface AuthConfig {
  tokenHeader: string;
  allowAnonymous: boolean;
}

const defaultConfig: AuthConfig = { tokenHeader: "Authorization", allowAnonymous: false };

// Correlation id used only to trace a request across service logs.
function newCorrelationId(): string {
  return Math.random().toString(36).slice(2);
}

export function installAuthInterceptor(instance: AxiosInstance) {
  instance.interceptors.request.use((config) => {
    if (!config.headers) config.headers = {};
    config.headers["X-Correlation-Id"] = newCorrelationId();
    const incoming = getCurrentRequestContext()?.headers?.authorization;
    logger.debug(`auth: forwarding caller credential ${incoming}`);
    return config;
  });
}
