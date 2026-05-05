using System;
using System.Collections.Generic;
using System.Linq;

namespace Game.Core.Services;

/// <summary>
/// Provides a deny-by-default policy gate for external process requests.
/// This guard does not execute commands; it only evaluates and audits requests.
/// </summary>
public sealed class ExternalProcessGuard
{
    private readonly AuditLogger auditLogger;
    private readonly Func<string, string?> readEnvironment;

    public ExternalProcessGuard(AuditLogger auditLogger, Func<string, string?>? readEnvironment = null)
    {
        this.auditLogger = auditLogger ?? throw new ArgumentNullException(nameof(auditLogger));
        this.readEnvironment = readEnvironment ?? Environment.GetEnvironmentVariable;
    }

    public ExternalProcessDecision Evaluate(ExternalProcessRequest request, DateTimeOffset? timestampUtc = null)
    {
        if (string.IsNullOrWhiteSpace(request.Command))
        {
            return Deny("empty_command", request, timestampUtc);
        }

        if (!IsDevModeEnabled())
        {
            return Deny("dev_mode_disabled", request, timestampUtc);
        }

        var command = NormalizeToken(request.Command);
        var allowlist = BuildAllowlist();
        if (!allowlist.Contains(command))
        {
            return Deny("command_not_allowlisted", request, timestampUtc);
        }

        var target = BuildTarget(request.Command, request.Arguments);
        auditLogger.Record("process.exec.allow", "allowlist_hit", target, request.Caller, timestampUtc);
        return ExternalProcessDecision.Allow("allowlist_hit");
    }

    private ExternalProcessDecision Deny(string reason, ExternalProcessRequest request, DateTimeOffset? timestampUtc)
    {
        var target = BuildTarget(request.Command, request.Arguments);
        auditLogger.Record("process.exec.deny", reason, target, request.Caller, timestampUtc);
        return ExternalProcessDecision.Deny(reason);
    }

    private bool IsDevModeEnabled()
    {
        var raw = (readEnvironment("SECURITY_TEST_MODE") ?? string.Empty).Trim();
        return string.Equals(raw, "1", StringComparison.OrdinalIgnoreCase)
               || string.Equals(raw, "true", StringComparison.OrdinalIgnoreCase);
    }

    private HashSet<string> BuildAllowlist()
    {
        var allowlist = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "dotnet",
            "py",
            "python",
        };

        var raw = readEnvironment("SECURITY_PROCESS_ALLOWLIST") ?? string.Empty;
        var tokens = raw.Split(new[] { ';', ',', '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        foreach (var token in tokens)
        {
            var normalized = NormalizeToken(token);
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                allowlist.Add(normalized);
            }
        }

        return allowlist;
    }

    private static string BuildTarget(string command, IReadOnlyList<string> arguments)
    {
        var safeCommand = (command ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(safeCommand))
        {
            safeCommand = "<empty-command>";
        }

        var safeArgs = arguments.Select(arg => arg ?? string.Empty).ToArray();
        return safeArgs.Length == 0 ? safeCommand : $"{safeCommand} {string.Join(" ", safeArgs)}";
    }

    private static string NormalizeToken(string value)
    {
        return (value ?? string.Empty).Trim().ToLowerInvariant();
    }
}

public sealed record ExternalProcessRequest(string Command, IReadOnlyList<string> Arguments, string Caller);

public sealed record ExternalProcessDecision(bool IsAllowed, string Reason)
{
    public static ExternalProcessDecision Allow(string reason) => new(true, reason);

    public static ExternalProcessDecision Deny(string reason) => new(false, reason);
}
