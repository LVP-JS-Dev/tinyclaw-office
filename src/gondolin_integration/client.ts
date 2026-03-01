/**
 * Gondolin API client for sandboxed code execution.
 *
 * This module provides a high-level client interface for executing code
 * in Gondolin sandboxes with automatic lifecycle management, secure
 * network policies, and comprehensive error handling.
 *
 * @example
 * ```typescript
 * import { GondolinClient } from './client.js';
 *
 * const client = new GondolinClient();
 * await client.initialize();
 *
 * const result = await client.executeCode('npm install', {
 *   allowedHosts: ['registry.npmjs.org'],
 *   secrets: { NPM_TOKEN: { hosts: ['registry.npmjs.org'], value: '...' } }
 * });
 *
 * console.log(result.stdout);
 * await client.shutdown();
 * ```
 */

import {
  SandboxManager,
  createSandbox,
  executeCommand,
  type SandboxConfig,
  type SecretConfig,
  type ExecutionResult,
  type ExecutionOptions,
  SandboxError,
  VMCreationError,
  ExecutionError,
  TimeoutError,
  VMCleanupError,
} from "./sandbox.js";

// ------------------------------------------------------------------------------
// Type Definitions
// ------------------------------------------------------------------------------

/**
 * Configuration for code execution requests.
 */
export interface ExecutionRequest {
  /** The command to execute */
  command: string;
  /** Allowed hosts for network access */
  allowedHosts: string[];
  /** Optional secrets to inject, scoped to specific hosts */
  secrets?: Record<string, SecretConfig>;
  /** Timeout in milliseconds (overrides default) */
  timeout?: number;
  /** Working directory inside the VM */
  cwd?: string;
  /** Environment variables to set for this execution */
  env?: Record<string, string>;
}

/**
 * Configuration for batch execution requests.
 */
export interface BatchExecutionRequest {
  /** Array of commands to execute sequentially */
  commands: string[];
  /** Allowed hosts for network access */
  allowedHosts: string[];
  /** Optional secrets to inject */
  secrets?: Record<string, SecretConfig>;
  /** Timeout in milliseconds per command */
  timeout?: number;
  /** Working directory inside the VM */
  cwd?: string;
  /** Environment variables for all commands */
  env?: Record<string, string>;
  /** Whether to stop on first error (default: true) */
  stopOnError?: boolean;
}

/**
 * Health check result.
 */
export interface HealthStatus {
  /** Whether the service is healthy */
  healthy: boolean;
  /** Whether QEMU is available */
  qemuAvailable: boolean;
  /** ARM64 architecture check */
  arm64Platform: boolean;
  /** Timestamp of the health check */
  timestamp: string;
}

/**
 * Client status information.
 */
export interface ClientStatus {
  /** Whether the client is initialized */
  initialized: boolean;
  /** Current sandbox status (if initialized) */
  sandbox?: {
    active: boolean;
    configured: boolean;
    config: {
      allowedHosts: string[];
      defaultTimeout: number;
      maxMemory: number;
      cpuCount: number;
    };
  };
}

// ------------------------------------------------------------------------------
// Structured Logger
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

// ------------------------------------------------------------------------------
// Gondolin Client
// ------------------------------------------------------------------------------

/**
 * High-level client for Gondolin sandboxed code execution.
 *
 * This client provides a simplified API for executing code in Gondolin
 * sandboxes with automatic lifecycle management and error handling.
 */
export class GondolinClient {
  private readonly logger: Logger;
  private sandbox: SandboxManager | null = null;
  private _initialized = false;

  /**
   * Default configuration for sandbox execution.
   */
  private readonly defaultConfig = {
    maxMemory: 512,
    cpuCount: 1,
    defaultTimeout: 60000,
  };

  constructor() {
    this.logger = new Logger("gondolin_integration.client");
    this.logger.info("Gondolin client initialized");
  }

  /**
   * Initialize the client.
   *
   * This method must be called before executing code. It verifies
   * that QEMU is available and the platform is ARM64.
   *
   * @throws VMCreationError if QEMU is not available or platform check fails
   */
  async initialize(): Promise<void> {
    if (this._initialized) {
      this.logger.debug("Client already initialized");
      return;
    }

    try {
      // Check platform requirements
      const health = await this.healthCheck();

      if (!health.arm64Platform) {
        throw new VMCreationError("Gondolin requires ARM64 platform", {
          platform: process.platform,
          arch: process.arch,
        });
      }

      if (!health.qemuAvailable) {
        throw new VMCreationError("QEMU is not available", {
          hint: "Install QEMU: brew install qemu (macOS) or apt install qemu (Linux)",
        });
      }

      this._initialized = true;
      this.logger.info("Gondolin client initialized successfully", {
        qemuAvailable: health.qemuAvailable,
        arm64Platform: health.arm64Platform,
      });

    } catch (error) {
      this.logger.error("Failed to initialize client", {
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  /**
   * Shutdown the client and release resources.
   *
   * This method closes any active sandbox and cleans up resources.
   */
  async shutdown(): Promise<void> {
    if (this.sandbox) {
      try {
        await this.sandbox.close();
        this.logger.info("Sandbox closed during shutdown");
      } catch (error) {
        this.logger.warn("Error closing sandbox during shutdown", {
          error: error instanceof Error ? error.message : String(error),
        });
      } finally {
        this.sandbox = null;
      }
    }

    this._initialized = false;
    this.logger.info("Gondolin client shutdown complete");
  }

  /**
   * Ensure the client is initialized.
   *
   * @throws Error if client is not initialized
   */
  private ensureInitialized(): void {
    if (!this._initialized) {
      throw new SandboxError("Client not initialized. Call initialize() first.", {
        method: "check_init",
      });
    }
  }

  /**
   * Check the health of the Gondolin environment.
   *
   * @returns Health status with QEMU availability and platform info
   */
  async healthCheck(): Promise<HealthStatus> {
    try {
      // Check for QEMU by attempting to run it
      const { exec } = await import("child_process");

      const qemuCheck = new Promise<boolean>((resolve) => {
        exec("qemu-system-aarch64 --version", (error) => {
          resolve(!error);
        });
      });

      const qemuAvailable = await qemuCheck;
      const arm64Platform = process.arch === "arm64";

      const health: HealthStatus = {
        healthy: qemuAvailable && arm64Platform,
        qemuAvailable,
        arm64Platform,
        timestamp: new Date().toISOString(),
      };

      this.logger.debug("Health check completed", health);
      return health;

    } catch (error) {
      this.logger.warn("Health check failed", {
        error: error instanceof Error ? error.message : String(error),
      });
      return {
        healthy: false,
        qemuAvailable: false,
        arm64Platform: process.arch === "arm64",
        timestamp: new Date().toISOString(),
      };
    }
  }

  /**
   * Get the current status of the client.
   *
   * @returns Client status information
   */
  getStatus(): ClientStatus {
    const status: ClientStatus = {
      initialized: this._initialized,
    };

    if (this.sandbox) {
      status.sandbox = this.sandbox.getStatus();
    }

    return status;
  }

  // ------------------------------------------------------------------------------
  // Single Execution Methods
  // ------------------------------------------------------------------------------

  /**
   * Execute a command with automatic sandbox lifecycle management.
   *
   * This is the simplest way to execute code - it creates a sandbox,
   * runs the command, and cleans up automatically.
   *
   * @param request - Execution request with command and configuration
   * @returns Execution result with stdout, stderr, exit code
   *
   * @example
   * ```typescript
   * const result = await client.executeOnce({
   *   command: 'npm install',
   *   allowedHosts: ['registry.npmjs.org'],
   *   timeout: 30000,
   * });
   * console.log(result.stdout);
   * ```
   */
  async executeOnce(request: ExecutionRequest): Promise<ExecutionResult> {
    this.ensureInitialized();

    const { command, allowedHosts, secrets, timeout, cwd, env } = request;

    this.logger.info("Executing command (once)", {
      command,
      allowedHosts,
      timeout,
    });

    try {
      const result = await executeCommand(
        command,
        {
          allowedHosts,
          secrets,
          defaultTimeout: timeout ?? this.defaultConfig.defaultTimeout,
          maxMemory: this.defaultConfig.maxMemory,
          cpuCount: this.defaultConfig.cpuCount,
        },
        {
          timeout,
          cwd,
          env,
          throwOnError: true,
        },
      );

      this.logger.info("Command completed successfully", {
        command,
        exitCode: result.exitCode,
        duration: result.duration,
      });

      return result;

    } catch (error) {
      this.logger.error("Command execution failed", {
        command,
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  }

  // ------------------------------------------------------------------------------
  // Persistent Sandbox Methods
  // ------------------------------------------------------------------------------

  /**
   * Create a persistent sandbox for multiple executions.
   *
   * Use this when you need to execute multiple commands in the same
   * VM context. Remember to call closeSandbox() when done.
   *
   * @param config - Sandbox configuration with allowed hosts and secrets
   *
   * @example
   * ```typescript
   * await client.createSandbox({
   *   allowedHosts: ['api.github.com'],
   *   secrets: { GITHUB_TOKEN: { hosts: ['api.github.com'], value: '...' } }
   * });
   *
   * await client.execute('npm install');
   * await client.execute('npm test');
   *
   * await client.closeSandbox();
   * ```
   */
  async createSandbox(config: Omit<SandboxConfig, "defaultTimeout" | "maxMemory" | "cpuCount">): Promise<void> {
    this.ensureInitialized();

    if (this.sandbox) {
      this.logger.warn("Sandbox already exists, closing existing sandbox");
      await this.closeSandbox();
    }

    this.logger.info("Creating persistent sandbox", {
      allowedHosts: config.allowedHosts,
      secretCount: Object.keys(config.secrets ?? {}).length,
    });

    this.sandbox = createSandbox({
      ...config,
      defaultTimeout: this.defaultConfig.defaultTimeout,
      maxMemory: this.defaultConfig.maxMemory,
      cpuCount: this.defaultConfig.cpuCount,
    });

    await this.sandbox.initialize();
    this.logger.info("Persistent sandbox created successfully");
  }

  /**
   * Execute a command in the persistent sandbox.
   *
   * @param command - Command to execute
   * @param options - Optional execution parameters
   * @returns Execution result
   * @throws SandboxError if no sandbox exists
   */
  async execute(command: string, options: ExecutionOptions = {}): Promise<ExecutionResult> {
    this.ensureInitialized();

    if (!this.sandbox) {
      throw new SandboxError("No sandbox exists. Call createSandbox() first.", {
        method: "execute",
      });
    }

    this.logger.debug("Executing command in persistent sandbox", {
      command,
      timeout: options.timeout,
    });

    return this.sandbox.execute(command, options);
  }

  /**
   * Execute multiple commands sequentially in the persistent sandbox.
   *
   * @param commands - Array of commands to execute
   * @param options - Optional execution parameters
   * @returns Array of execution results
   * @throws SandboxError if no sandbox exists
   */
  async executeBatch(commands: string[], options: ExecutionOptions = {}): Promise<ExecutionResult[]> {
    this.ensureInitialized();

    if (!this.sandbox) {
      throw new SandboxError("No sandbox exists. Call createSandbox() first.", {
        method: "executeBatch",
      });
    }

    this.logger.info("Executing batch in persistent sandbox", {
      commandCount: commands.length,
    });

    return this.sandbox.executeBatch(commands, options);
  }

  /**
   * Check if a persistent sandbox is active.
   *
   * @returns True if sandbox exists and is active
   */
  hasSandbox(): boolean {
    return this.sandbox !== null && this.sandbox.isActive();
  }

  /**
   * Close the persistent sandbox.
   *
   * This releases the VM and associated resources.
   */
  async closeSandbox(): Promise<void> {
    if (this.sandbox) {
      this.logger.info("Closing persistent sandbox");
      await this.sandbox.close();
      this.sandbox = null;
      this.logger.info("Persistent sandbox closed");
    }
  }

  // ------------------------------------------------------------------------------
  // Convenience Methods
  // ------------------------------------------------------------------------------

  /**
   * Execute Node.js code in a sandbox.
   *
   * @param code - JavaScript/TypeScript code to execute
   * @param request - Execution configuration
   * @returns Execution result
   *
   * @example
   * ```typescript
   * const result = await client.executeNode(
   *   'console.log("Hello, world!");',
   *   { allowedHosts: [] }
   * );
   * ```
   */
  async executeNode(code: string, request: Omit<ExecutionRequest, "command">): Promise<ExecutionResult> {
    const command = `node -e "${code.replace(/"/g, '\\"')}"`;
    return this.executeOnce({ ...request, command });
  }

  /**
   * Execute Python code in a sandbox.
   *
   * @param code - Python code to execute
   * @param request - Execution configuration
   * @returns Execution result
   *
   * @example
   * ```typescript
   * const result = await client.executePython(
   *   'print("Hello, world!")',
   *   { allowedHosts: [] }
   * );
   * ```
   */
  async executePython(code: string, request: Omit<ExecutionRequest, "command">): Promise<ExecutionResult> {
    const command = `python3 -c "${code.replace(/"/g, '\\"')}"`;
    return this.executeOnce({ ...request, command });
  }

  /**
   * Execute a shell script in a sandbox.
   *
   * @param script - Shell script content
   * @param request - Execution configuration
   * @returns Execution result
   *
   * @example
   * ```typescript
   * const result = await client.executeScript(
   *   'echo "Hello" && echo "World"',
   *   { allowedHosts: [] }
   * );
   * ```
   */
  async executeScript(script: string, request: Omit<ExecutionRequest, "command">): Promise<ExecutionResult> {
    const command = `sh -c "${script.replace(/"/g, '\\"')}"`;
    return this.executeOnce({ ...request, command });
  }
}

// ------------------------------------------------------------------------------
// Helper Functions
// ------------------------------------------------------------------------------

/**
 * Create a new Gondolin client instance.
 *
 * This is a convenience function for creating a client.
 *
 * @returns New GondolinClient instance
 *
 * @example
 * ```typescript
 * const client = createClient();
 * await client.initialize();
 * const result = await client.executeOnce({
 *   command: 'echo "Hello, world!"',
 *   allowedHosts: []
 * });
 * await client.shutdown();
 * ```
 */
export function createClient(): GondolinClient {
  return new GondolinClient();
}

/**
 * Execute a command with automatic client lifecycle management.
 *
 * This is the simplest way to execute a single command.
 *
 * @param command - Command to execute
 * @param config - Sandbox configuration
 * @param options - Optional execution parameters
 * @returns Execution result
 *
 * @example
 * ```typescript
 * const result = await execute('npm install', {
 *   allowedHosts: ['registry.npmjs.org'],
 *   secrets: { NPM_TOKEN: { hosts: ['registry.npmjs.org'], value: '...' } }
 * }, { timeout: 30000 });
 * console.log(result.stdout);
 * ```
 */
export async function execute(
  command: string,
  config: Omit<SandboxConfig, "defaultTimeout" | "maxMemory" | "cpuCount">,
  options?: Omit<ExecutionOptions, "throwOnError">,
): Promise<ExecutionResult> {
  const client = new GondolinClient();
  try {
    await client.initialize();
    return await client.executeOnce({
      command,
      allowedHosts: config.allowedHosts,
      secrets: config.secrets,
      timeout: options?.timeout,
      cwd: options?.cwd,
      env: options?.env,
    });
  } finally {
    await client.shutdown();
  }
}

// Export all public types, classes, and functions
export type {
  SandboxConfig,
  SecretConfig,
  ExecutionResult,
  ExecutionOptions,
  ExecutionRequest,
  BatchExecutionRequest,
  HealthStatus,
  ClientStatus,
};

export {
  SandboxError,
  VMCreationError,
  ExecutionError,
  TimeoutError,
  VMCleanupError,
};
