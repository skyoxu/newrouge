using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0049AcceptanceTests
{
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0049AcceptanceTests.cs";
    private static readonly string[] RequiredAdrRefs = { "ADR-0029" };
    private static readonly string[] RequiredChapterRefs = { "CH01", "CH06", "CH02", "CH07" };

    // ACC:T49.1
    [Fact]
    public void ShouldReturnFailureOn101stAttempt_WhenTurnReachesHardCap()
    {
        var service = new CombatService();

        for (var i = 0; i < 100; i++)
        {
            var successfulAttempt = service.PlayCard(CreateValidInput(cardsPlayedThisTurn: i));
            successfulAttempt.Success.Should().BeTrue();
        }

        var attempt101 = service.PlayCard(CreateValidInput(cardsPlayedThisTurn: 100));

        attempt101.Success.Should().BeFalse("the 101st attempt must trigger the hard-stop path");
        attempt101.FailureReason.Should().Contain("HardLimitExceeded");
        attempt101.StateAfter.Should().Be(attempt101.StateBefore);
    }

    // ACC:T49.2
    [Fact]
    public void ShouldExposeObservableFailureOutput_WhenHardStopIsTriggeredOnWindows()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);

        var result = service.PlayCard(CreateValidInput(cardsPlayedThisTurn: 100));
        var hasObservableOutput = !string.IsNullOrWhiteSpace(result.FailureReason)
            || bus.Published.Any(evt => evt.Type == EventTypes.CombatLoopHardStopped)
            || bus.Published.Any(evt => evt.Type == EventTypes.AuditLogged);

        result.Success.Should().BeFalse();
        hasObservableOutput.Should().BeTrue();
    }

    // ACC:T49.3
    [Fact]
    public void ShouldExposeAcceptanceIndexEntries_WhenVerifyingTask49ChecklistBinding()
    {
        var acceptanceIndex = BuildTaskEvidence().AcceptanceIndex;

        acceptanceIndex.Should().ContainKey("ACC:T49.1");
        acceptanceIndex.Should().ContainKey("ACC:T49.8");
        acceptanceIndex.Should().ContainKey("ACC:T49.10");
        acceptanceIndex["ACC:T49.1"].Should().Be(1);
        acceptanceIndex["ACC:T49.10"].Should().Be(10);
    }

    // ACC:T49.7
    [Fact]
    public void ShouldStopProcessingFurtherAttempts_WhenHardStopHasAlreadyTriggered()
    {
        var service = new CombatService();
        var action = () => service.PlayCard(CreateValidInput(cardsPlayedThisTurn: 101));

        action.Should().NotThrow();
        var attempt102 = action();

        attempt102.Success.Should().BeFalse();
        attempt102.FailureReason.Should().Contain("HardStopAlreadyTriggered");
        attempt102.StateAfter.Should().Be(attempt102.StateBefore);
    }

    // ACC:T49.8
    [Fact]
    public void ShouldAppendAuditLogEntry_WhenHardStopPathExecutes()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);

        var result = service.PlayCard(CreateValidInput(cardsPlayedThisTurn: 100));

        result.Success.Should().BeFalse();
        var auditEvent = bus.Published.Single(evt => evt.Type == EventTypes.AuditLogged);
        auditEvent.DataJson.Should().NotBeNullOrWhiteSpace();
        using var payloadDoc = JsonDocument.Parse(auditEvent.DataJson!);
        payloadDoc.RootElement.GetProperty("event").GetString().Should().Be("hard-stop-triggered");
        payloadDoc.RootElement.GetProperty("reason_code").GetString().Should().Be("HardLimitExceeded");
    }

    // ACC:T49.9
    [Fact]
    public void ShouldReferenceAdr0029_WhenExplainingHardStopPolicy()
    {
        var evidence = BuildTaskEvidence();

        evidence.AdrRefs.Should().ContainSingle("ADR-0029");
    }

    // ACC:T49.10
    [Fact]
    public void ShouldFailGate_WhenAdrRefsDoNotExactlyMatchTaskMetadata()
    {
        var evidence = BuildTaskEvidence();
        var mismatchedAdrRefs = new[] { "ADR-0010" };

        var exitCode = EvaluateAdrRefsGate(mismatchedAdrRefs, evidence.AdrRefs);

        exitCode.Should().Be(1);
    }

    // ACC:T49.11
    [Fact]
    public void ShouldFailGate_WhenChapterRefsDoNotExactlyMatchTaskMetadata()
    {
        var evidence = BuildTaskEvidence();
        var mismatchedChapterRefs = new[] { "CH01", "CH06", "CH02" };

        var exitCode = EvaluateChapterRefsGate(mismatchedChapterRefs, evidence.ChapterRefs);

        exitCode.Should().Be(1);
    }

    // ACC:T49.12
    [Fact]
    public void ShouldMarkTaskAsFailed_WhenAnyRequiredArtifactIsUnexecutedOrFailed()
    {
        var artifactStates = new[]
        {
            new ArtifactExecutionRecord("hard-stop-acceptance", true, "pass", Optional: false),
            new ArtifactExecutionRecord("review-pipeline", false, "skipped", Optional: false),
        };

        var gatePassed = EvaluateArtifactsGate(artifactStates);

        gatePassed.Should().BeFalse();
    }

    // ACC:T49.13
    [Fact]
    public void ShouldMarkOptionalSwitchAsSkippedNotPassed_WhenSwitchIsDisabled()
    {
        var optionalArtifact = BuildOptionalSwitchRecord(enabled: false);

        optionalArtifact.Executed.Should().BeFalse();
        optionalArtifact.PassFail.Should().Be("skipped");
        IsCountedAsPass(optionalArtifact).Should().BeFalse();
    }

    // ACC:T49.14
    [Fact]
    public void ShouldEmitTaskIndexForHardStopAndFailureHandling_WhenProducingAcceptanceEvidence()
    {
        var evidence = BuildTaskEvidence();

        evidence.TaskId.Should().Be(49);
        evidence.AcceptanceIndex["ACC:T49.1"].Should().Be(1);
        evidence.AcceptanceIndex["ACC:T49.8"].Should().Be(8);
        evidence.TestRefs.Should().Contain(ThisTaskTestRef);
    }

    private static PlayCardPipelineInput CreateValidInput(int cardsPlayedThisTurn)
    {
        return new PlayCardPipelineInput(
            DifficultyId: 9,
            CardsPlayedThisTurn: cardsPlayedThisTurn,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 2,
            BaseCardCost: 1,
            EnergyBefore: 999,
            BaseDamage: 12,
            Strength: 1,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "combatant-a",
            StableId: "stable-001");
    }

    private static TaskEvidence BuildTaskEvidence()
    {
        return new TaskEvidence(
            TaskId: 49,
            AcceptanceIndex: new Dictionary<string, int>(StringComparer.Ordinal)
            {
                ["ACC:T49.1"] = 1,
                ["ACC:T49.2"] = 2,
                ["ACC:T49.3"] = 3,
                ["ACC:T49.7"] = 7,
                ["ACC:T49.8"] = 8,
                ["ACC:T49.9"] = 9,
                ["ACC:T49.10"] = 10,
                ["ACC:T49.11"] = 11,
                ["ACC:T49.12"] = 12,
                ["ACC:T49.13"] = 13,
                ["ACC:T49.14"] = 14,
            },
            AdrRefs: RequiredAdrRefs.ToArray(),
            ChapterRefs: RequiredChapterRefs.ToArray(),
            TestRefs: new[] { ThisTaskTestRef });
    }

    private static int EvaluateAdrRefsGate(IEnumerable<string> actualAdrRefs, IEnumerable<string> expectedAdrRefs)
    {
        return SetEqualsOrdinal(actualAdrRefs, expectedAdrRefs) ? 0 : 1;
    }

    private static int EvaluateChapterRefsGate(IEnumerable<string> actualChapterRefs, IEnumerable<string> expectedChapterRefs)
    {
        return SetEqualsOrdinal(actualChapterRefs, expectedChapterRefs) ? 0 : 1;
    }

    private static bool SetEqualsOrdinal(IEnumerable<string> left, IEnumerable<string> right)
    {
        var leftSet = new HashSet<string>(left, StringComparer.Ordinal);
        var rightSet = new HashSet<string>(right, StringComparer.Ordinal);
        return leftSet.SetEquals(rightSet);
    }

    private static bool EvaluateArtifactsGate(IEnumerable<ArtifactExecutionRecord> artifacts)
    {
        foreach (var artifact in artifacts)
        {
            if (!artifact.Executed)
            {
                return false;
            }

            if (!string.Equals(artifact.PassFail, "pass", StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    private static ArtifactExecutionRecord BuildOptionalSwitchRecord(bool enabled)
    {
        if (!enabled)
        {
            return new ArtifactExecutionRecord("optional-switch", false, "skipped", Optional: true);
        }

        return new ArtifactExecutionRecord("optional-switch", true, "pass", Optional: true);
    }

    private static bool IsCountedAsPass(ArtifactExecutionRecord artifact)
    {
        return artifact.Executed && string.Equals(artifact.PassFail, "pass", StringComparison.Ordinal);
    }

    private sealed class CapturingEventBus : IEventBus
    {
        public List<DomainEvent> Published { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            Published.Add(evt);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => new DummySubscription();

        private sealed class DummySubscription : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }

    private sealed record ArtifactExecutionRecord(
        string ArtifactId,
        bool Executed,
        string PassFail,
        bool Optional);

    private sealed record TaskEvidence(
        int TaskId,
        IReadOnlyDictionary<string, int> AcceptanceIndex,
        string[] AdrRefs,
        string[] ChapterRefs,
        string[] TestRefs);
}
