/**
 * Shared structured logging module for Gondolin integration.
 *
 * This module provides a simple structured logger that outputs JSON-formatted
 * log entries to stdout, matching the Python logging pattern used elsewhere
 * in the project.
 *
 * @example
 * ```typescript
 * import { Logger } from './logging.js';
 *
 * const logger = new Logger('my_module');
 * logger.info('Operation started', { taskId: 123 });
 * logger.error('Operation failed', { error: 'Something went wrong' });
 * ```
 */

// ------------------------------------------------------------------------------
// Structured Logger (JSON format)
// ------------------------------------------------------------------------------

/**
 * Simple structured logger for JSON output (matches Python logging pattern).
 *
 * Outputs log entries as JSON objects to stdout, one per line. Each entry
 * includes a timestamp, log level, logger context, message, and any additional
 * fields passed as extra data.
 */
export class Logger {
  /**
   * Create a new Logger instance.
   *
   * @param context - The logger context name (typically module name)
   */
  constructor(private readonly context: string) {}

  /**
   * Internal method to format and output a log entry.
   *
   * @param level - Log level (INFO, WARN, ERROR, DEBUG)
   * @param message - The log message
   * @param extra - Optional additional fields to include
   */
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

  /**
   * Log an informational message.
   *
   * @param message - The log message
   * @param extra - Optional additional fields to include
   */
  info(message: string, extra?: Record<string, unknown>): void {
    this.log("INFO", message, extra);
  }

  /**
   * Log a warning message.
   *
   * @param message - The log message
   * @param extra - Optional additional fields to include
   */
  warn(message: string, extra?: Record<string, unknown>): void {
    this.log("WARN", message, extra);
  }

  /**
   * Log an error message.
   *
   * @param message - The log message
   * @param extra - Optional additional fields to include
   */
  error(message: string, extra?: Record<string, unknown>): void {
    this.log("ERROR", message, extra);
  }

  /**
   * Log a debug message.
   *
   * @param message - The log message
   * @param extra - Optional additional fields to include
   */
  debug(message: string, extra?: Record<string, unknown>): void {
    this.log("DEBUG", message, extra);
  }
}
