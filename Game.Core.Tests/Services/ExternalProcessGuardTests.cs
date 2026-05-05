using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T93")]
[Trait("adr", "ADR-0019")]
public sealed class ExternalProcessGuardTests
{
    [Fact]
    public void ShouldDenyByDefault_WhenDevModeIsDisabled()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var guard = CreateGuard(logger, new Dictionary<string, string?>
        {
            ["SECURITY_TEST_MODE"] = "0",
            ["SECURITY_PROCESS_ALLOWLIST"] = "dotnet,py",
        });

        var ts = new DateTimeOffset(2026, 5, 5, 14, 0, 0, TimeSpan.Zero);
        var decision = guard.Evaluate(
            new ExternalProcessRequest("dotnet", new[] { "--version" }, "Task0093AcceptanceTests"),
            ts);

        decision.IsAllowed.Should().BeFalse();
        decision.Reason.Should().Be("dev_mode_disabled");

        var entry = ReadAuditEntries(logger.BuildAbsolutePath(ts)).Should().ContainSingle().Subject;
        entry.Action.Should().Be("process.exec.deny");
        entry.Reason.Should().Be("dev_mode_disabled");
        entry.Target.Should().Contain("dotnet");
        entry.Target.Should().Contain("--version");
        entry.Caller.Should().Be("Task0093AcceptanceTests");
    }

    [Fact]
    public void ShouldAllowWhenDevModeEnabledAndCommandIsAllowlisted()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var guard = CreateGuard(logger, new Dictionary<string, string?>
        {
            ["SECURITY_TEST_MODE"] = "1",
            ["SECURITY_PROCESS_ALLOWLIST"] = "dotnet,py",
        });

        var ts = new DateTimeOffset(2026, 5, 5, 14, 0, 1, TimeSpan.Zero);
        var decision = guard.Evaluate(
            new ExternalProcessRequest("dotnet", new[] { "--version" }, "Task0093AcceptanceTests"),
            ts);

        decision.IsAllowed.Should().BeTrue();
        decision.Reason.Should().Be("allowlist_hit");

        var entry = ReadAuditEntries(logger.BuildAbsolutePath(ts)).Should().ContainSingle().Subject;
        entry.Action.Should().Be("process.exec.allow");
        entry.Reason.Should().Be("allowlist_hit");
        entry.Target.Should().Contain("dotnet");
        entry.Target.Should().Contain("--version");
        entry.Caller.Should().Be("Task0093AcceptanceTests");
    }

    [Fact]
    public void ShouldDenyWhenDevModeEnabledButCommandIsNotAllowlisted()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var guard = CreateGuard(logger, new Dictionary<string, string?>
        {
            ["SECURITY_TEST_MODE"] = "1",
            ["SECURITY_PROCESS_ALLOWLIST"] = "dotnet,py",
        });

        var ts = new DateTimeOffset(2026, 5, 5, 14, 0, 2, TimeSpan.Zero);
        var decision = guard.Evaluate(
            new ExternalProcessRequest("powershell", new[] { "-NoProfile" }, "Task0093AcceptanceTests"),
            ts);

        decision.IsAllowed.Should().BeFalse();
        decision.Reason.Should().Be("command_not_allowlisted");

        var entry = ReadAuditEntries(logger.BuildAbsolutePath(ts)).Should().ContainSingle().Subject;
        entry.Action.Should().Be("process.exec.deny");
        entry.Reason.Should().Be("command_not_allowlisted");
        entry.Target.Should().Contain("powershell");
        entry.Target.Should().Contain("-NoProfile");
        entry.Caller.Should().Be("Task0093AcceptanceTests");
    }

    [Fact]
    public void ShouldDenyEmptyCommandAndStillWriteAudit()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var guard = CreateGuard(logger, new Dictionary<string, string?>
        {
            ["SECURITY_TEST_MODE"] = "1",
            ["SECURITY_PROCESS_ALLOWLIST"] = "dotnet,py",
        });

        var ts = new DateTimeOffset(2026, 5, 5, 14, 0, 3, TimeSpan.Zero);
        var decision = guard.Evaluate(
            new ExternalProcessRequest(" ", Array.Empty<string>(), "Task0093AcceptanceTests"),
            ts);

        decision.IsAllowed.Should().BeFalse();
        decision.Reason.Should().Be("empty_command");

        var entry = ReadAuditEntries(logger.BuildAbsolutePath(ts)).Should().ContainSingle().Subject;
        entry.Action.Should().Be("process.exec.deny");
        entry.Reason.Should().Be("empty_command");
        entry.Target.Should().Be("<empty-command>");
        entry.Caller.Should().Be("Task0093AcceptanceTests");
    }

    private static ExternalProcessGuard CreateGuard(AuditLogger logger, IReadOnlyDictionary<string, string?> env)
    {
        return new ExternalProcessGuard(
            logger,
            key => env.TryGetValue(key, out var value) ? value : null);
    }

    private static IReadOnlyList<AuditEntry> ReadAuditEntries(string path)
    {
        File.Exists(path).Should().BeTrue();
        var lines = File.ReadAllText(path)
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        var entries = new List<AuditEntry>(lines.Length);
        foreach (var line in lines)
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            entries.Add(new AuditEntry(
                root.GetProperty("action").GetString() ?? string.Empty,
                root.GetProperty("reason").GetString() ?? string.Empty,
                root.GetProperty("target").GetString() ?? string.Empty,
                root.GetProperty("caller").GetString() ?? string.Empty));
        }

        return entries;
    }

    private sealed record AuditEntry(string Action, string Reason, string Target, string Caller);

    private sealed class RepoSandbox : IDisposable
    {
        public RepoSandbox()
        {
            RootPath = Path.Combine(Path.GetTempPath(), "newrouge-task93-process-guard-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(RootPath);
        }

        public string RootPath { get; }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(RootPath))
                {
                    Directory.Delete(RootPath, recursive: true);
                }
            }
            catch
            {
                // best effort
            }
        }
    }
}
