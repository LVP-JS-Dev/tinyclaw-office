/**
 * Gondolin sandbox wrapper with VM lifecycle management.
 *
 * This module provides a wrapper around Gondolin's VM functionality with:
 * - Automatic VM lifecycle management (create, execute, cleanup)
 * - Secure network policy enforcement via HTTP hooks
 * - Scoped secret injection for external API access
 * - Resource limits and timeouts
 * - Comprehensive error handling and logging
 *
 * @example
 * ```typescript
 * import { SandboxManager } from './sandbox.js';
 *
 * const manager = new SandboxManager({
 *   allowedHosts: ['api.github.com'],
 *   secrets: { GITHUB_TOKEN: { hosts: ['api.github.com'], value: '...' } }
 * });
 *
 * const result = await manager.execute('npm install', { timeout: 30000 });
 * console.log(result.stdout, result.stderr);
 * ```
 */

import { createHttpHooks, VM } from "@earendil-works/gondolin";

// ------------------------------------------------------------------------------
// Type Definitions
// ------------------------------------------------------------------------------

/**
 * Configuration for secret injection into VM network requests.
 */
export interface SecretConfig {
  /** Hosts this secret can be used with (whitelist approach) */
  hosts: string[];
  /** The secret value (typically from environment variable) */
  value: string;
}

/**
 * Configuration options for creating a sandbox.
 */
export interface SandboxConfig {
  /** Allowed hosts for network access (whitelist approach) */
  allowedHosts: string[];
  /** Secrets to inject, scoped to specific hosts */
  secrets?: Record<string, SecretConfig>;
  /** Default timeout for commands in milliseconds (default: 60000) */
  defaultTimeout?: number;
  /** Maximum memory for VM in MB (default: 512) */
  maxMemory?: number;
  /** Number of CPU cores (default: 1) */
  cpuCount?: number;
}

/**
 * Execution result from a sandboxed command.
 */
export interface ExecutionResult {
  /** The command that was executed */
  command: string;
  /** Exit code (0 = success, non-zero = error) */
  exitCode: number;
  /** Standard output from the command */
  stdout: string;
  /** Standard error from the command */
  stderr: string;
  /** Whether the command completed within the timeout */
  timedOut: boolean;
  /** Execution time in milliseconds */
  duration: number;
}

/**
 * Options for a single execution.
 */
export interface ExecutionOptions {
  /** Timeout in milliseconds (overrides sandbox default) */
  timeout?: number;
  /** Working directory inside the VM */
  cwd?: string;
  /** Environment variables to set for this execution */
  env?: Record<string, string>;
  /** Whether to throw on non-zero exit codes (default: true) */
  throwOnError?: boolean;
}

// ------------------------------------------------------------------------------
// Custom Errors
// ------------------------------------------------------------------------------

/**
 * Base error for all Sandbox-related errors.
 */
export class SandboxError extends Error {
  constructor(message: string, public readonly details?: Record<string, unknown>) {
    super(message);
    this.name = "SandboxError";
  }
}

/**
 * Error raised when VM creation fails.
 */
export class VMCreationError extends SandboxError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "VMCreationError";
  }
}

/**
 * Error raised when command execution fails or times out.
 */
export class ExecutionError extends SandboxError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "ExecutionError";
  }
}

/**
 * Error raised when command times out.
 */
export class TimeoutError extends ExecutionError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "TimeoutError";
  }
}

/**
 * Error raised when VM cleanup fails.
 */
export class VMCleanupError extends SandboxError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(message, details);
    this.name = "VMCleanupError";
  }
}

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

// ------------------------------------------------------------------------------
// Sandbox Manager
// ------------------------------------------------------------------------------

/**
 * Manages Gondolin VM lifecycle with automatic cleanup.
 *
 * This class provides a high-level interface for creating and managing
 * sandboxed VMs with proper resource limits and security policies.
 */
export class SandboxManager {
  private vm: VM | null = null;
  private readonly logger: Logger;
  private readonly config: Required<Pick<SandboxConfig, "defaultTimeout" | "maxMemory" | "cpuCount">>;

  /**
   * Create a new SandboxManager.
   *
   * @param config - Sandbox configuration
   */
  constructor(
    private readonly sandboxConfig: SandboxConfig,
  ) {
    this.logger = new Logger("gondolin_integration.sandbox");
    this.config = {
      defaultTimeout: sandboxConfig.defaultTimeout ?? 60000,
      maxMemory: sandboxConfig.maxMemory ?? 512,
      cpuCount: sandboxConfig.cpuCount ?? 1,
    };

    this.logger.info("SandboxManager initialized", {
      allowedHosts: sandboxConfig.allowedHosts,
      secretCount: Object.keys(sandboxConfig.secrets ?? {}).length,
      defaultTimeout: this.config.defaultTimeout,
      maxMemory: this.config.maxMemory,
      cpuCount: this.config.cpuCount,
    });
  }

  /**
   * Create HTTP hooks with network policy and secret injection.
   *
   * @returns Gondolin HTTP hooks configuration
   */
  private createHttpHooks(): ReturnType<typeof createHttpHooks> {
    const { allowedHosts, secrets } = this.sandboxConfig;

    // Build secrets configuration for Gondolin
    const gondolinSecrets: Record<string, { hosts: string[]; value: string }> = {};
    if (secrets) {
      for (const [key, config] of Object.entries(secrets)) {
        gondolinSecrets[key] = {
          hosts: config.hosts,
          value: config.value,
        };
      }
    }

    this.logger.debug("Creating HTTP hooks", {
      allowedHosts,
      secrets: Object.keys(gondolinSecrets),
    });

    return createHttpHooks({
      allowedHosts,
      secrets: gondolinSecrets,
    });
  }

  /**
   * Initialize the VM.
   *
   * This creates a new QEMU VM with the configured security policies.
   * The VM will be automatically cleaned up when close() is called.
   *
   * @throws VMCreationError if VM creation fails
   */
  async initialize(): Promise<void> {
    if (this.vm) {
      this.logger.warn("VM already initialized");
      return;
    }

    try {
      this.logger.info("Initializing VM", {
        maxMemory: this.config.maxMemory,
        cpuCount: this.config.cpuCount,
      });

      const { httpHooks, env } = this.createHttpHooks();

      this.vm = await VM.create({
        httpHooks,
        env,
        maxMemory: this.config.maxMemory,
        cpuCount: this.config.cpuCount,
      });

      this.logger.info("VM initialized successfully");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.error("VM initialization failed", { error: message });
      throw new VMCreationError("Failed to initialize VM", { originalError: message });
    }
  }

  /**
   * Ensure VM is initialized, creating if necessary.
   *
   * @throws VMCreationError if auto-initialization fails
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.vm) {
      await this.initialize();
    }
  }

  /**
   * Execute a command in the sandbox.
   *
   * @param command - The command to execute
   * @param options - Execution options
   * @returns Execution result with stdout, stderr, exit code
   * @throws ExecutionError if execution fails and throwOnError is true
   */
  async execute(command: string, options: ExecutionOptions = {}): Promise<ExecutionResult> {
    await this.ensureInitialized();

    const timeout = options.timeout ?? this.config.defaultTimeout;
    const startTime = Date.now();

    this.logger.info("Executing command", {
      command,
      timeout,
      cwd: options.cwd,
      throwOnError: options.throwOnError ?? true,
    });

    try {
      if (!this.vm) {
        throw new ExecutionError("VM not initialized");
      }

      // Execute with timeout
      const result = await this.executeWithTimeout(command, timeout, options);
      const duration = Date.now() - startTime;

      const executionResult: ExecutionResult = {
        command,
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
        timedOut: result.timedOut,
        duration,
      };

      // Log result
      this.logger.info("Command completed", {
        command,
        exitCode: executionResult.exitCode,
        duration,
        timedOut: executionResult.timedOut,
        stdoutLength: executionResult.stdout.length,
        stderrLength: executionResult.stderr.length,
      });

      // Check for error conditions
      if (executionResult.timedOut) {
        const timeoutError = new TimeoutError("Command timed out", {
          command,
          timeout,
          duration,
        });
        if (options.throwOnError ?? true) {
          throw timeoutError;
        }
      }

      if (executionResult.exitCode !== 0 && (options.throwOnError ?? true)) {
        throw new ExecutionError("Command failed with non-zero exit code", {
          command,
          exitCode: executionResult.exitCode,
          stderr: executionResult.stderr,
        });
      }

      return executionResult;
    } catch (error) {
      if (error instanceof ExecutionError || error instanceof TimeoutError) {
        throw error;
      }

      const message = error instanceof Error ? error.message : String(error);
      this.logger.error("Command execution failed", {
        command,
        error: message,
        duration: Date.now() - startTime,
      });

      throw new ExecutionError("Command execution failed", {
        command,
        originalError: message,
      });
    }
  }

  /**
   * Execute command with timeout enforcement.
   *
   * @param command - Command to execute
   * @param timeout - Timeout in milliseconds
   * @param options - Execution options
   * @returns Execution result
   */
  private async executeWithTimeout(
    command: string,
    timeout: number,
    options: ExecutionOptions,
  ): Promise<Omit<ExecutionResult, "command" | "duration">> {
    if (!this.vm) {
      throw new Error("VM not initialized");
    }

    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    // Create a timeout promise
    const timeoutPromise = new Promise<Omit<ExecutionResult, "command" | "duration">>(
      (resolve) => {
        timeoutId = setTimeout(() => {
          resolve({
            exitCode: -1,
            stdout: "",
            stderr: `Command timed out after ${timeout}ms`,
            timedOut: true,
          });
        }, timeout);
      },
    );

    // Create the execution promise
    const executionPromise = (async (): Promise<Omit<ExecutionResult, "command" | "duration">> => {
      try {
        const result = await this.vm.exec(command, {
          cwd: options.cwd,
          env: options.env,
        });

        return {
          exitCode: result.exitCode ?? 0,
          stdout: result.stdout ?? "",
          stderr: result.stderr ?? "",
          timedOut: false,
        };
      } catch (error) {
        return {
          exitCode: -1,
          stdout: "",
          stderr: error instanceof Error ? error.message : String(error),
          timedOut: false,
        };
      }
    })();

    try {
      // Race between execution and timeout
      const result = await Promise.race([timeoutPromise, executionPromise]);

      // If timeout occurred, clean up the VM
      if (result.timedOut) {
        await this.close();
      }

      return result;
    } finally {
      // Clear timeout to prevent memory leaks
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    }
  }

  /**
   * Execute multiple commands sequentially.
   *
   * @param commands - Array of commands to execute
   * @param options - Execution options applied to all commands
   * @returns Array of execution results
   */
  async executeBatch(
    commands: string[],
    options: ExecutionOptions = {},
  ): Promise<ExecutionResult[]> {
    this.logger.info("Executing batch", {
      commandCount: commands.length,
      timeout: options.timeout ?? this.config.defaultTimeout,
    });

    const results: ExecutionResult[] = [];

    for (const command of commands) {
      const result = await this.execute(command, options);
      results.push(result);

      // Stop if a command failed and throwOnError is true
      if (result.exitCode !== 0 && (options.throwOnError ?? true)) {
        this.logger.warn("Batch execution stopped due to error", {
          command,
          exitCode: result.exitCode,
        });
        break;
      }
    }

    return results;
  }

  /**
   * Check if the VM is currently active.
   *
   * @returns True if VM is initialized and running
   */
  isActive(): boolean {
    return this.vm !== null;
  }

  /**
   * Get VM statistics.
   *
   * @returns VM status information
   */
  getStatus(): {
    active: boolean;
    configured: boolean;
    config: Pick<SandboxConfig, "allowedHosts"> &
      Required<Pick<SandboxConfig, "defaultTimeout" | "maxMemory" | "cpuCount">>;
  } {
    return {
      active: this.isActive(),
      configured: true,
      config: {
        ...this.config,
        allowedHosts: this.sandboxConfig.allowedHosts,
      },
    };
  }

  /**
   * Close the VM and release resources.
   *
   * This should always be called when done with the sandbox to ensure
   * proper cleanup of QEMU resources.
   *
   * @throws VMCleanupError if cleanup fails
   */
  async close(): Promise<void> {
    if (!this.vm) {
      this.logger.debug("No VM to close");
      return;
    }

    try {
      this.logger.info("Closing VM");
      await this.vm.close();
      this.vm = null;
      this.logger.info("VM closed successfully");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.logger.error("VM cleanup failed", { error: message });
      throw new VMCleanupError("Failed to close VM", { originalError: message });
    }
  }

  /**
   * Execute a command with automatic lifecycle management.
   *
   * This is a convenience method that initializes the VM, executes the
   * command, and cleans up automatically.
   *
   * @param command - Command to execute
   * @param options - Execution options
   * @returns Execution result
   */
  async executeOnce(command: string, options: ExecutionOptions = {}): Promise<ExecutionResult> {
    try {
      await this.initialize();
      return await this.execute(command, options);
    } finally {
      await this.close();
    }
  }
}

// ------------------------------------------------------------------------------
// Helper Functions
// ------------------------------------------------------------------------------

/**
 * Create a sandbox manager with default configuration.
 *
 * @param config - Sandbox configuration
 * @returns New SandboxManager instance
 */
export function createSandbox(config: SandboxConfig): SandboxManager {
  return new SandboxManager(config);
}

/**
 * Execute a single command with automatic cleanup.
 *
 * This is the simplest way to run a sandboxed command.
 *
 * @param command - Command to execute
 * @param config - Sandbox configuration
 * @param options - Execution options
 * @returns Execution result
 *
 * @example
 * ```typescript
 * const result = await executeCommand(
 *   'npm install',
 *   { allowedHosts: ['registry.npmjs.org'] },
 *   { timeout: 30000 }
 * );
 * console.log(result.stdout);
 * ```
 */
export async function executeCommand(
  command: string,
  config: SandboxConfig,
  options: ExecutionOptions = {},
): Promise<ExecutionResult> {
  const manager = new SandboxManager(config);
  return manager.executeOnce(command, options);
}

// Export all public types and functions
export type {
  SandboxConfig,
  SecretConfig,
  ExecutionResult,
  ExecutionOptions,
};
