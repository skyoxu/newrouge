using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Status;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0005AcceptanceTests
{
    // ACC:T5.1
    [Fact]
    public void ShouldContainRequiredEnumsAndStatusFields_WhenCheckingStatusContracts()
    {
        Enum.GetNames(typeof(StatusType)).Should().BeEquivalentTo("Buff", "Debuff", "RuleModifier");
        typeof(ExpiresTiming).IsEnum.Should().BeTrue();
        typeof(Status).IsClass.Should().BeTrue();

        var status = NewCanonicalStatus(
            stableId: "stable-001",
            statusId: "status.strength",
            statusType: StatusType.Buff,
            stacks: 1,
            durationTurns: 2,
            sourceId: "source-A",
            expiresTiming: ExpiresTiming.OwnerEndOfTurnCleanup,
            strength: 3);

        status.StatusId.Should().Be("status.strength");
        status.StableId.Should().Be("stable-001");
        status.Stacks.Should().Be(1);
        status.DurationTurns.Should().Be(2);
        status.SourceId.Should().Be("source-A");
        status.ExpiresTiming.Should().Be(ExpiresTiming.OwnerEndOfTurnCleanup);
        status.Strength.Should().Be(3);
    }

    // ACC:T5.2
    [Fact]
    public void ShouldProduceDeterministicSequenceAndNoopApply_WhenRunningSameOperations()
    {
        var left = NewStatus("stable-001", "status.guard", StatusType.Buff, 2, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 1);
        var right = NewStatus("stable-001", "status.guard", StatusType.Buff, 2, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 1);
        var incoming = NewStatus("stable-002", "status.guard", StatusType.Buff, 1, 2, "source-B", ExpiresTiming.OwnerEndOfTurnCleanup, 2);
        var mismatch = NewStatus("stable-003", "status.poison", StatusType.Debuff, 1, 2, "source-C", ExpiresTiming.OwnerEndOfTurnCleanup, 2);
        var noop = incoming with { Stacks = 0, DurationTurns = 0, Strength = 0 };

        var leftFinal = left.StackWith(incoming).AccumulateDuration(2).Decay(1);
        var rightFinal = right.StackWith(incoming).AccumulateDuration(2).Decay(1);

        leftFinal.Should().Be(rightFinal);
        left.StackWith(noop).Should().Be(left);
        left.StackWith(mismatch).Should().Be(left);
    }

    // ACC:T5.3
    [Fact]
    public void ShouldCoverStackDurationDispelAndStableIdOrdering_WhenCheckingRules()
    {
        var ruleModifier = NewStatus("stable-r", "status.rule", StatusType.RuleModifier, 1, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 0);
        var strengthStatus = NewStatus("stable-s", StatusOperations.StrengthStatusId, StatusType.Buff, 1, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 2);
        var normalDebuff = NewStatus("stable-d", "status.poison", StatusType.Debuff, 1, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 5);

        StatusOperations.CanDispel(ruleModifier).Should().BeFalse();
        StatusOperations.CanDispel(strengthStatus).Should().BeFalse();
        StatusOperations.CanDispel(normalDebuff).Should().BeTrue();

        var remaining = StatusOperations.Dispel(new[] { ruleModifier, strengthStatus, normalDebuff });
        remaining.Should().Contain(x => x.StatusType == StatusType.RuleModifier);
        remaining.Should().Contain(x => x.StatusId == StatusOperations.StrengthStatusId);
        remaining.Should().NotContain(x => x.StatusId == "status.poison");

        var sorted = StatusOperations.SortByStableId(new[]
        {
            NewStatus("stable-002", "status.b", StatusType.Buff, 1, 2, "source-B", ExpiresTiming.OwnerEndOfTurnCleanup, 0),
            NewStatus("stable-001", "status.c", StatusType.Buff, 1, 2, "source-C", ExpiresTiming.OwnerEndOfTurnCleanup, 0),
            NewStatus("stable-001", "status.a", StatusType.Buff, 1, 2, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 0),
        });
        sorted.Select(x => $"{x.StableId}|{x.StatusId}")
            .Should()
            .Equal("stable-001|status.a", "stable-001|status.c", "stable-002|status.b");
    }

    // ACC:T5.4
    [Fact]
    public void ShouldExposeCallableStackAccumulateAndDecayOnStatus_WhenCheckingContractMethods()
    {
        var current = NewStatus("stable-001", "status.guard", StatusType.Buff, 2, 3, "source-A", ExpiresTiming.OwnerEndOfTurnCleanup, 1);
        var incoming = NewStatus("stable-002", "status.guard", StatusType.Buff, 1, 2, "source-B", ExpiresTiming.OwnerEndOfTurnCleanup, 2);

        var stacked = current.StackWith(incoming);
        stacked.Stacks.Should().Be(3);
        stacked.DurationTurns.Should().Be(5);
        stacked.Strength.Should().Be(3);

        var accumulated = stacked.AccumulateDuration(3);
        accumulated.DurationTurns.Should().Be(8);

        var decayed = accumulated.Decay(2);
        decayed.DurationTurns.Should().Be(6);
    }

    // ACC:T5.5
    [Fact]
    public void ShouldContainAdrRefsInTaskViews_WhenCheckingAdrBacklinks()
    {
        var root = ResolveRepoRoot();
        var backRefs = ParseTaskAdrRefs(Path.Combine(root, ".taskmaster", "tasks", "tasks_back.json"));
        var gameplayRefs = ParseTaskAdrRefs(Path.Combine(root, ".taskmaster", "tasks", "tasks_gameplay.json"));

        backRefs.Should().BeEquivalentTo("ADR-0021", "ADR-0029");
        gameplayRefs.Should().BeEquivalentTo("ADR-0021", "ADR-0029");
    }

    // ACC:T5.6
    [Fact]
    public void ShouldKeepAdrRefsConsistentAcrossChecklistAndTaskViews_WhenCheckingAdrMapping()
    {
        var root = ResolveRepoRoot();
        var checklistPath = Path.Combine(root, "docs", "architecture", "overlays", "PRD-NEWROUGE-GAME-0001", "08", "ACCEPTANCE_CHECKLIST.md");
        var checklist = File.ReadAllText(checklistPath);
        var checklistRefs = ParseChecklistTask5AdrRefs(checklist);

        checklistRefs.Should().BeEquivalentTo("ADR-0021", "ADR-0029");
        ParseTaskAdrRefs(Path.Combine(root, ".taskmaster", "tasks", "tasks_back.json"))
            .Should()
            .BeEquivalentTo(checklistRefs);
        ParseTaskAdrRefs(Path.Combine(root, ".taskmaster", "tasks", "tasks_gameplay.json"))
            .Should()
            .BeEquivalentTo(checklistRefs);
    }

    // ACC:T5.7
    [Fact]
    public void ShouldUseClassShapeForStatusContract_WhenCheckingTaskContract()
    {
        typeof(Status).IsClass.Should().BeTrue();
        var status = NewCanonicalStatus("stable-100", "status.guard", StatusType.Buff, 1, 2, "source-z", ExpiresTiming.OwnerEndOfTurnCleanup, 1);
        var instance = NewStatus(status.StableId, status.StatusId, status.StatusType, status.Stacks, status.DurationTurns, status.SourceId, status.ExpiresTiming, status.Strength);
        instance.StatusId.Should().Be(status.StatusId);
        instance.StatusType.Should().Be(status.StatusType);
    }

    private static string[] ParseTaskAdrRefs(string path)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var row = doc.RootElement
            .EnumerateArray()
            .First(x => x.TryGetProperty("taskmaster_id", out var id) && id.ToString() == "5");
        return row.GetProperty("adr_refs").EnumerateArray().Select(x => x.GetString() ?? string.Empty).ToArray();
    }

    private static string[] ParseChecklistTask5AdrRefs(string checklist)
    {
        const string section = "## Task5 ADR Mapping";
        var index = checklist.IndexOf(section, StringComparison.Ordinal);
        index.Should().BeGreaterOrEqualTo(0, "checklist must include Task5 ADR Mapping section");

        var start = index + section.Length;
        var nextSection = checklist.IndexOf("\n## ", start, StringComparison.Ordinal);
        var slice = nextSection >= 0
            ? checklist[index..nextSection]
            : checklist[index..];
        return slice
            .Split('\n')
            .Select(line => line.Trim())
            .Where(line => line.StartsWith("- ADR-", StringComparison.Ordinal))
            .Select(line => line.TrimStart('-').Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current != null)
        {
            if (File.Exists(Path.Combine(current.FullName, "AGENTS.md")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Unable to resolve repository root.");
    }

    private static StatusInstance NewStatus(
        string stableId,
        string statusId,
        StatusType statusType,
        int stacks,
        int durationTurns,
        string sourceId,
        ExpiresTiming expiresTiming,
        int strength)
    {
        return new StatusInstance(
            StableId: stableId,
            StatusId: statusId,
            StatusType: statusType,
            Stacks: stacks,
            DurationTurns: durationTurns,
            SourceId: sourceId,
            ExpiresTiming: expiresTiming,
            Strength: strength);
    }

    private static Status NewCanonicalStatus(
        string stableId,
        string statusId,
        StatusType statusType,
        int stacks,
        int durationTurns,
        string sourceId,
        ExpiresTiming expiresTiming,
        int strength)
    {
        return new Status(
            StableId: stableId,
            StatusId: statusId,
            StatusType: statusType,
            Stacks: stacks,
            DurationTurns: durationTurns,
            SourceId: sourceId,
            ExpiresTiming: expiresTiming,
            Strength: strength);
    }
}
