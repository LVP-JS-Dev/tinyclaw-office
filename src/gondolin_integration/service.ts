/**
 * Gondolin integration service with Express.js API.
 *
 * This module provides the main Express application for the Gondolin integration,
 * exposing endpoints for sandboxed code execution with secure network policies.
 *
 * @example
 * ```bash
 * npm run start
 * # Service runs on port 9000
 * curl http://localhost:9000/health
 * ```
 */

import express, { type Express, type Request, type Response, type NextFunction } from "express";
import { GondolinClient, createClient, type ExecutionRequest, type ExecutionOptions } from "./client.js";
import type { ExecutionResult, HealthStatus, ClientStatus } from "./client.js";

// ------------------------------------------------------------------------------
// Configuration
// ------------------------------------------------------------------------------

const PORT = parseInt(process.env.GONDOLIN_PORT || "9000", 10);
const HOST = process.env.GONDOLIN_HOST || "0.0.0.0";

// ------------------------------------------------------------------------------
// Structured Logger (JSON format)
// ------------------------------------------------------------------------------

/**
 * Simple structured logger for JSON output (matches Python logging pattern).
 */
class Logger {
  constructor(private readonly context: string) {}

  private log(level: string, message: string, extra?: Record<string, unknown>): void {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level,
      logger: this.context,
      message,
      ...extra,
    };
    process.stdout.write(JSON.stringify(logEntry) + "\n");
  }

  info(message: string, extra?: Record<string, unknown>): void {
    this.log("INFO", message, extra);
  }

  warn(message: string, extra?: Record<string, unknown>): void {
    this.log("WARN", message, extra);
  }

  error(message: string, extra?: Record<string, unknown>): void {
    this.log("ERROR", message, extra);
  }

  debug(message: string, extra?: Record<string, unknown>): void {
    this.log("DEBUG", message, extra);
  }
}

const logger = new Logger("gondolin_integration.service");

// ------------------------------------------------------------------------------
// Error Handling
// ------------------------------------------------------------------------------

/**
 * Base error class for API errors.
 */
export class APIError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "APIError";
  }
}

/**
 * Validation error (400).
 */
export class ValidationError extends APIError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 400, details);
    this.name = "ValidationError";
  }
}

/**
 * Integration error (503).
 */
export class IntegrationError extends APIError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, 503, details);
    this.name = "IntegrationError";
  }
}

// ------------------------------------------------------------------------------
// Global Client
// ------------------------------------------------------------------------------

let gondolinClient: GondolinClient | null = null;

/**
 * Get the global Gondolin client instance.
 *
 * @returns GondolinClient instance
 * @throws IntegrationError if client is not initialized
 */
function getClient(): GondolinClient {
  if (!gondolinClient) {
    throw new IntegrationError("Gondolin client not initialized", {
      service: "gondolin_integration",
    });
  }
  return gondolinClient;
}

// ------------------------------------------------------------------------------
// Express App
// ------------------------------------------------------------------------------

const app: Express = express();

// Parse JSON request bodies
app.use(express.json());

// Request logging middleware
app.use((req: Request, _res: Response, next: NextFunction) => {
  logger.debug("Incoming request", {
    method: req.method,
    path: req.path,
    query: req.query,
  });
  next();
});

// ------------------------------------------------------------------------------
// Lifecycle Management
// ------------------------------------------------------------------------------

/**
 * Initialize the service.
 *
 * This function starts the Gondolin client and performs initial health checks.
 */
async function initialize(): Promise<void> {
  logger.info("Starting Gondolin integration service");

  try {
    // Create and initialize client
    gondolinClient = createClient();
    await gondolinClient.initialize();

    // Perform health check
    const health = await gondolinClient.healthCheck();
    if (health.healthy) {
      logger.info("Gondolin environment healthy", {
        qemuAvailable: health.qemuAvailable,
        arm64Platform: health.arm64Platform,
      });
    } else {
      logger.warn("Gondolin health check failed, but continuing", {
        qemuAvailable: health.qemuAvailable,
        arm64Platform: health.arm64Platform,
      });
    }

    logger.info("Gondolin integration service started successfully");
  } catch (error) {
    logger.error("Failed to start Gondolin integration service", {
      error: error instanceof Error ? error.message : String(error),
    });
    // Don't throw - allow service to start in degraded mode
    gondolinClient = null;
  }
}

/**
 * Shutdown the service.
 *
 * This function gracefully shuts down the Gondolin client.
 */
async function shutdown(): Promise<void> {
  logger.info("Shutting down Gondolin integration service");

  if (gondolinClient) {
    try {
      await gondolinClient.shutdown();
      logger.info("Gondolin client shutdown complete");
    } catch (error) {
      logger.warn("Error during shutdown", {
        error: error instanceof Error ? error.message : String(error),
      });
    }
    gondolinClient = null;
  }

  logger.info("Gondolin integration service shutdown complete");
}

// ------------------------------------------------------------------------------
// Error Handlers
// ------------------------------------------------------------------------------

/**
 * Handle API errors.
 */
function apiErrorHandler(
  err: Error,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  if (err instanceof APIError) {
    logger.warn("API error", {
      error_type: err.name,
      message: err.message,
      status_code: err.statusCode,
      details: err.details,
    });

    res.status(err.statusCode).json({
      error: err.name,
      message: err.message,
      details: err.details,
    });
    return;
  }

  // Unknown error
  logger.error("Unexpected error", {
    error: err.message,
    stack: err.stack,
  });

  res.status(500).json({
    error: "InternalError",
    message: "An unexpected error occurred",
  });
}

// ------------------------------------------------------------------------------
// Routes
// ------------------------------------------------------------------------------

/**
 * GET /health
 *
 * Health check endpoint.
 *
 * @returns Health status with QEMU availability and platform info
 */
app.get("/health", async (_req: Request, res: Response): Promise<void> => {
  try {
    const client = getClient();
    const health: HealthStatus = await client.healthCheck();

    res.status(200).json({
      status: "healthy",
      service: "gondolin_integration",
      ...health,
    });
  } catch (error) {
    const health: HealthStatus = {
      healthy: false,
      qemuAvailable: false,
      arm64Platform: process.arch === "arm64",
      timestamp: new Date().toISOString(),
    };

    res.status(503).json({
      status: "unhealthy",
      service: "gondolin_integration",
      ...health,
    });
  }
});

/**
 * GET /api/status
 *
 * Get the current status of the Gondolin client.
 *
 * @returns Client status information
 */
app.get("/api/status", (_req: Request, res: Response): void => {
  try {
    const client = getClient();
    const status: ClientStatus = client.getStatus();

    res.status(200).json(status);
  } catch (error) {
    res.status(503).json({
      error: "Service unavailable",
      message: error instanceof Error ? error.message : "Client not initialized",
    });
  }
});

// ------------------------------------------------------------------------------
// Execution Endpoints (One-shot)
// ------------------------------------------------------------------------------

/**
 * POST /api/execute
 *
 * Execute a command with automatic sandbox lifecycle management.
 *
 * Request body:
 * - command: string - The command to execute
 * - allowedHosts: string[] - Allowed hosts for network access
 * - secrets?: Record<string, SecretConfig> - Optional secrets to inject
 * - timeout?: number - Timeout in milliseconds
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 *
 * @returns Execution result with stdout, stderr, exit code, duration
 */
app.post("/api/execute", async (req: Request, res: Response): Promise<void> => {
  try {
    const { command, allowedHosts, secrets, timeout, cwd, env } = req.body;

    // Validate request
    if (!command || typeof command !== "string") {
      throw new ValidationError("command is required and must be a string");
    }

    if (!allowedHosts || !Array.isArray(allowedHosts)) {
      throw new ValidationError("allowedHosts is required and must be an array");
    }

    if (!allowedHosts.every((h: unknown) => typeof h === "string")) {
      throw new ValidationError("all allowedHosts entries must be strings");
    }

    const client = getClient();
    const executionRequest: ExecutionRequest = {
      command,
      allowedHosts,
      secrets,
      timeout,
      cwd,
      env,
    };

    logger.info("Executing command (once)", {
      command,
      allowedHosts,
      timeout,
    });

    const result: ExecutionResult = await client.executeOnce(executionRequest);

    logger.info("Command completed successfully", {
      command,
      exitCode: result.exitCode,
      duration: result.duration,
    });

    res.status(200).json({
      success: true,
      result: {
        command: result.command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration: result.duration,
      },
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    logger.error("Command execution failed", {
      command: req.body?.command,
      error: error instanceof Error ? error.message : String(error),
    });

    throw new IntegrationError("Command execution failed", {
      command: req.body?.command,
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * POST /api/execute/node
 *
 * Execute Node.js code in a sandbox.
 *
 * Request body:
 * - code: string - JavaScript/TypeScript code to execute
 * - allowedHosts: string[] - Allowed hosts for network access
 * - secrets?: Record<string, SecretConfig> - Optional secrets to inject
 * - timeout?: number - Timeout in milliseconds
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 *
 * @returns Execution result
 */
app.post("/api/execute/node", async (req: Request, res: Response): Promise<void> => {
  try {
    const { code, allowedHosts, secrets, timeout, cwd, env } = req.body;

    // Validate request
    if (!code || typeof code !== "string") {
      throw new ValidationError("code is required and must be a string");
    }

    if (!allowedHosts || !Array.isArray(allowedHosts)) {
      throw new ValidationError("allowedHosts is required and must be an array");
    }

    const client = getClient();
    const result = await client.executeNode(code, {
      allowedHosts,
      secrets,
      timeout,
      cwd,
      env,
    });

    logger.info("Node.js execution completed", {
      exitCode: result.exitCode,
      duration: result.duration,
    });

    res.status(200).json({
      success: true,
      result: {
        command: result.command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration: result.duration,
      },
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Node.js execution failed", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * POST /api/execute/python
 *
 * Execute Python code in a sandbox.
 *
 * Request body:
 * - code: string - Python code to execute
 * - allowedHosts: string[] - Allowed hosts for network access
 * - secrets?: Record<string, SecretConfig> - Optional secrets to inject
 * - timeout?: number - Timeout in milliseconds
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 *
 * @returns Execution result
 */
app.post("/api/execute/python", async (req: Request, res: Response): Promise<void> => {
  try {
    const { code, allowedHosts, secrets, timeout, cwd, env } = req.body;

    // Validate request
    if (!code || typeof code !== "string") {
      throw new ValidationError("code is required and must be a string");
    }

    if (!allowedHosts || !Array.isArray(allowedHosts)) {
      throw new ValidationError("allowedHosts is required and must be an array");
    }

    const client = getClient();
    const result = await client.executePython(code, {
      allowedHosts,
      secrets,
      timeout,
      cwd,
      env,
    });

    logger.info("Python execution completed", {
      exitCode: result.exitCode,
      duration: result.duration,
    });

    res.status(200).json({
      success: true,
      result: {
        command: result.command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration: result.duration,
      },
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Python execution failed", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * POST /api/execute/script
 *
 * Execute a shell script in a sandbox.
 *
 * Request body:
 * - script: string - Shell script content
 * - allowedHosts: string[] - Allowed hosts for network access
 * - secrets?: Record<string, SecretConfig> - Optional secrets to inject
 * - timeout?: number - Timeout in milliseconds
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 *
 * @returns Execution result
 */
app.post("/api/execute/script", async (req: Request, res: Response): Promise<void> => {
  try {
    const { script, allowedHosts, secrets, timeout, cwd, env } = req.body;

    // Validate request
    if (!script || typeof script !== "string") {
      throw new ValidationError("script is required and must be a string");
    }

    if (!allowedHosts || !Array.isArray(allowedHosts)) {
      throw new ValidationError("allowedHosts is required and must be an array");
    }

    const client = getClient();
    const result = await client.executeScript(script, {
      allowedHosts,
      secrets,
      timeout,
      cwd,
      env,
    });

    logger.info("Script execution completed", {
      exitCode: result.exitCode,
      duration: result.duration,
    });

    res.status(200).json({
      success: true,
      result: {
        command: result.command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration: result.duration,
      },
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Script execution failed", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

// ------------------------------------------------------------------------------
// Persistent Sandbox Endpoints
// ------------------------------------------------------------------------------

/**
 * POST /api/sandbox
 *
 * Create a persistent sandbox for multiple executions.
 *
 * Request body:
 * - allowedHosts: string[] - Allowed hosts for network access
 * - secrets?: Record<string, SecretConfig> - Optional secrets to inject
 *
 * @returns Confirmation of sandbox creation
 */
app.post("/api/sandbox", async (req: Request, res: Response): Promise<void> => {
  try {
    const { allowedHosts, secrets } = req.body;

    // Validate request
    if (!allowedHosts || !Array.isArray(allowedHosts)) {
      throw new ValidationError("allowedHosts is required and must be an array");
    }

    const client = getClient();

    logger.info("Creating persistent sandbox", {
      allowedHosts,
      secretCount: Object.keys(secrets || {}).length,
    });

    await client.createSandbox({ allowedHosts, secrets });

    logger.info("Persistent sandbox created successfully");

    res.status(201).json({
      success: true,
      message: "Persistent sandbox created",
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Failed to create sandbox", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * POST /api/sandbox/execute
 *
 * Execute a command in the persistent sandbox.
 *
 * Request body:
 * - command: string - Command to execute
 * - timeout?: number - Timeout in milliseconds
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 *
 * @returns Execution result
 */
app.post("/api/sandbox/execute", async (req: Request, res: Response): Promise<void> => {
  try {
    const { command, timeout, cwd, env } = req.body;

    // Validate request
    if (!command || typeof command !== "string") {
      throw new ValidationError("command is required and must be a string");
    }

    const client = getClient();
    const options: ExecutionOptions = {
      timeout,
      cwd,
      env,
    };

    logger.debug("Executing command in persistent sandbox", {
      command,
      timeout,
    });

    const result = await client.execute(command, options);

    res.status(200).json({
      success: true,
      result: {
        command: result.command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration: result.duration,
      },
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Failed to execute command in sandbox", {
      command: req.body?.command,
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * POST /api/sandbox/batch
 *
 * Execute multiple commands sequentially in the persistent sandbox.
 *
 * Request body:
 * - commands: string[] - Array of commands to execute
 * - timeout?: number - Timeout in milliseconds per command
 * - cwd?: string - Working directory inside the VM
 * - env?: Record<string, string> - Environment variables
 * - stopOnError?: boolean - Whether to stop on first error (default: true)
 *
 * @returns Array of execution results
 */
app.post("/api/sandbox/batch", async (req: Request, res: Response): Promise<void> => {
  try {
    const { commands, timeout, cwd, env, stopOnError = true } = req.body;

    // Validate request
    if (!commands || !Array.isArray(commands)) {
      throw new ValidationError("commands is required and must be an array");
    }

    if (!commands.every((c: unknown) => typeof c === "string")) {
      throw new ValidationError("all commands must be strings");
    }

    const client = getClient();
    const options: ExecutionOptions = {
      timeout,
      cwd,
      env,
      throwOnError: stopOnError,
    };

    logger.info("Executing batch in persistent sandbox", {
      commandCount: commands.length,
    });

    const results = await client.executeBatch(commands, options);

    res.status(200).json({
      success: true,
      results: results.map((r) => ({
        command: r.command,
        exitCode: r.exitCode,
        stdout: r.stdout,
        stderr: r.stderr,
        timedOut: r.timedOut,
        duration: r.duration,
      })),
    });
  } catch (error) {
    if (error instanceof ValidationError) {
      throw error;
    }

    throw new IntegrationError("Failed to execute batch in sandbox", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * GET /api/sandbox/status
 *
 * Get the current status of the persistent sandbox.
 *
 * @returns Sandbox status information
 */
app.get("/api/sandbox/status", (_req: Request, res: Response): void => {
  try {
    const client = getClient();

    if (!client.hasSandbox()) {
      res.status(404).json({
        error: "No sandbox",
        message: "No persistent sandbox exists",
      });
      return;
    }

    const status = client.getStatus();
    res.status(200).json(status);
  } catch (error) {
    throw new IntegrationError("Failed to get sandbox status", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

/**
 * DELETE /api/sandbox
 *
 * Close the persistent sandbox.
 *
 * @returns Confirmation of sandbox closure
 */
app.delete("/api/sandbox", async (_req: Request, res: Response): Promise<void> => {
  try {
    const client = getClient();

    if (!client.hasSandbox()) {
      res.status(404).json({
        error: "No sandbox",
        message: "No persistent sandbox exists",
      });
      return;
    }

    logger.info("Closing persistent sandbox");

    await client.closeSandbox();

    logger.info("Persistent sandbox closed");

    res.status(200).json({
      success: true,
      message: "Persistent sandbox closed",
    });
  } catch (error) {
    throw new IntegrationError("Failed to close sandbox", {
      originalError: error instanceof Error ? error.message : String(error),
    });
  }
});

// ------------------------------------------------------------------------------
// 404 Handler
// ------------------------------------------------------------------------------

app.use((_req: Request, _res: Response, next: NextFunction): void => {
  next(new APIError("Not found", 404));
});

// ------------------------------------------------------------------------------
// Error Handler Middleware (must be last)
// ------------------------------------------------------------------------------

app.use(apiErrorHandler);

// ------------------------------------------------------------------------------
// Server Startup
// ------------------------------------------------------------------------------

/**
 * Start the Express server.
 */
async function start(): Promise<void> {
  await initialize();

  const server = app.listen(PORT, HOST, () => {
    logger.info(`Gondolin integration API listening on http://${HOST}:${PORT}`);
  });

  // Handle graceful shutdown
  const shutdownHandler = async (signal: string): Promise<void> => {
    logger.info(`Received ${signal}, shutting down gracefully`);
    server.close(async () => {
      await shutdown();
      process.exit(0);
    });

    // Force shutdown after 10 seconds
    setTimeout(() => {
      logger.error("Forced shutdown after timeout");
      process.exit(1);
    }, 10000);
  };

  process.on("SIGTERM", () => shutdownHandler("SIGTERM"));
  process.on("SIGINT", () => shutdownHandler("SIGINT"));
}

// Start the server if this file is run directly
if (import.meta.url === `file://${process.argv[1]}`) {
  start().catch((error) => {
    logger.error("Failed to start server", { error: error.message });
    process.exit(1);
  });
}

// Export for testing
export { app, initialize, shutdown };
