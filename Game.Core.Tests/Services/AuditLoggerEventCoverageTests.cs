using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T38")]
[Trait("adr", "ADR-0019")]
[Trait("adr", "ADR-0003")]
public sealed class AuditLoggerEventCoverageTests
{
    // ACC:T38.5
    [Fact]
    public void ShouldIncludeSaveLoadOfferLockAndDenyReason_WhenRefusalScenarioIsAudited()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var day = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);

        logger.RecordSave("slot-01", "SaveService.WriteAutosaveAsync", day);
        logger.RecordLoad("slot-01", "SaveService.ReadAutosaveAsync", day.AddSeconds(1));
        logger.RecordOfferLock("offer-01", "RewardOfferLockingService.Lock", day.AddSeconds(2));
        logger.RecordDeny("offer_lock_missing_nonce", "offer-01", "RewardOfferLockingService.Commit", day.AddSeconds(3));

        var path = logger.BuildAbsolutePath(day);
        File.Exists(path).Should().BeTrue();

        var entries = ReadEntries(path);
        entries.Select(x => x.Action).Should().ContainInOrder("save", "load", "offer_lock", "deny");
        entries.Should().HaveCount(4);

        var deny = entries.Single(x => string.Equals(x.Action, "deny", StringComparison.Ordinal));
        deny.Reason.Should().Be("offer_lock_missing_nonce");
        deny.Reason.Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public void ShouldNotRecordOfferAccepted_WhenOfferIsRefused()
    {
        using var sandbox = new RepoSandbox();
        var logger = new AuditLogger(sandbox.RootPath);
        var day = new DateTimeOffset(2026, 4, 18, 9, 0, 0, TimeSpan.Zero);

        logger.RecordOfferLock("offer-02", "RewardOfferLockingService.Lock", day);
        logger.RecordDeny("policy_block", "offer-02", "RewardOfferLockingService.Commit", day.AddSeconds(1));

        var path = logger.BuildAbsolutePath(day);
        var entries = ReadEntries(path);

        entries.Should().HaveCount(2);
        entries.Should().NotContain(x => string.Equals(x.Action, "offer_accepted", StringComparison.Ordinal));
    }

    private static IReadOnlyList<AuditEntry> ReadEntries(string path)
    {
        var lines = File.ReadAllText(path)
            .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        var entries = new List<AuditEntry>(lines.Length);
        foreach (var line in lines)
        {
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            entries.Add(new AuditEntry(
                Action: root.GetProperty("action").GetString() ?? string.Empty,
                Reason: root.GetProperty("reason").GetString() ?? string.Empty));
        }

        return entries;
    }

    private sealed record AuditEntry(string Action, string Reason);

    private sealed class RepoSandbox : IDisposable
    {
        public RepoSandbox()
        {
            RootPath = Path.Combine(Path.GetTempPath(), "newrouge-task38-" + Guid.NewGuid().ToString("N"));
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
