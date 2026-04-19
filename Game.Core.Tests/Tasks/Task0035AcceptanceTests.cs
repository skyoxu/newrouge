using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Run;
using Game.Core.Services;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0035AcceptanceTests
{
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0035AcceptanceTests.cs";
    private const string TasksGameplayPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string OverlayIndexPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md";

    // ACC:T35.1
    [Fact]
    public void ShouldTransitionToReward_WhenVictorySettlementSignalsAreCompleteAndOrdered()
    {
        var machine = BuildMachineAtCombatState();
        var payload = BuildVictorySettlementPayload(isComplete: true);
        CombatResolutionCommandPayload.TryParse(payload, out var parsedPayload).Should().BeTrue();
        parsedPayload.Should().NotBeNull();
        parsedPayload!.RunStatePersisted.Should().BeTrue();
        parsedPayload.RewardHandoff.Should().NotBeNull();
        parsedPayload.RewardHandoff!.RunSnapshotId.Should().NotBeNullOrWhiteSpace();
        parsedPayload.SettlementStages.Should().ContainInOrder(
            "death_triggers_resolved",
            "reward_offer_presented",
            "run_state_persisted");
        parsedPayload.SettlementStages.Last().Should().Be("run_state_persisted");

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-victory", "complete_combat", payload),
            out var transition);

        accepted.Should().BeTrue();
        transition.FromState.Should().Be(RunState.Combat);
        transition.ToState.Should().Be(RunState.Reward);
        machine.LastPersistedRunSnapshotId.Should().Be(parsedPayload.RewardHandoff.RunSnapshotId);
        machine.LastPersistenceSourceState.Should().Be(RunState.Combat);
        machine.CurrentState.Should().Be(RunState.Reward);
    }

    // ACC:T35.2
    [Fact]
    public void ShouldEndRunWithoutReward_WhenCombatResolutionIsDefeat()
    {
        var machine = BuildMachineAtCombatState();

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-defeat", "resolve_combat_defeat"),
            out var defeatTransition);

        accepted.Should().BeTrue();
        defeatTransition.FromState.Should().Be(RunState.Combat);
        defeatTransition.ToState.Should().Be(RunState.GameOver);
        machine.CurrentState.Should().Be(RunState.GameOver);

        var rewardClaimAccepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-defeat-claim", "claim_reward"),
            out var blockedTransition);
        rewardClaimAccepted.Should().BeFalse();
        blockedTransition.Reason.Should().Be("invalid_command_no_transition");
        machine.CurrentState.Should().NotBe(RunState.Reward);

        var returnToMenuAccepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-defeat-menu", "return_to_menu"),
            out var menuTransition);
        returnToMenuAccepted.Should().BeTrue();
        menuTransition.FromState.Should().Be(RunState.GameOver);
        menuTransition.ToState.Should().Be(RunState.MainMenu);
        machine.CurrentState.Should().Be(RunState.MainMenu);
        var rewardAfterMenuAccepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-defeat-reward-after-menu", "claim_reward"),
            out var rewardAfterMenuTransition);
        rewardAfterMenuAccepted.Should().BeFalse();
        rewardAfterMenuTransition.Reason.Should().Be("invalid_command_no_transition");
        machine.CurrentState.Should().Be(RunState.MainMenu);
        machine.CurrentState.Should().NotBe(RunState.Reward);
    }

    // ACC:T35.3
    [Fact]
    public void ShouldFailClosed_WhenVictorySettlementPayloadIsIncomplete()
    {
        var machine = BuildMachineAtCombatState();
        var payload = BuildVictorySettlementPayload(isComplete: false);
        var stateBefore = machine.CurrentState;
        var transitionCountBefore = machine.Transitions.Count;

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-incomplete", "complete_combat", payload),
            out var transition);

        accepted.Should().BeFalse();
        transition.Reason.Should().Be("invalid_command_no_transition");
        machine.LastPersistedRunSnapshotId.Should().BeNull();
        machine.CurrentState.Should().Be(stateBefore);
        machine.Transitions.Count.Should().Be(transitionCountBefore);
    }

    // ACC:T35.3
    [Theory]
    [InlineData("{")]
    [InlineData("\"not-an-object\"")]
    public void ShouldFailClosed_WhenVictorySettlementPayloadIsMalformed(string malformedPayload)
    {
        var machine = BuildMachineAtCombatState();
        var stateBefore = machine.CurrentState;
        var transitionCountBefore = machine.Transitions.Count;

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-malformed", "complete_combat", malformedPayload),
            out var transition);

        accepted.Should().BeFalse();
        transition.Reason.Should().Be("invalid_command_no_transition");
        machine.LastPersistedRunSnapshotId.Should().BeNull();
        machine.CurrentState.Should().Be(stateBefore);
        machine.Transitions.Count.Should().Be(transitionCountBefore);
    }

    // ACC:T35.3
    [Fact]
    public void ShouldFailClosed_WhenVictorySettlementPayloadMissesRequiredRunSnapshotMarker()
    {
        var machine = BuildMachineAtCombatState();
        var missingSnapshotPayload = JsonSerializer.Serialize(new
        {
            settlement_completed = true,
            death_triggers_resolved = true,
            reward_offer_presented = true,
            run_state_persisted = true,
            settlement_stages = new[] { "death_triggers_resolved", "reward_offer_presented", "run_state_persisted" },
            reward_handoff = new
            {
                reward_context_id = "reward.task35.missing-snapshot",
                offer_ids = new[] { "offer.task35.a", "offer.task35.b", "offer.task35.c" }
            }
        });

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-missing-snapshot", "complete_combat", missingSnapshotPayload),
            out var transition);

        accepted.Should().BeFalse();
        transition.Reason.Should().Be("invalid_command_no_transition");
        machine.LastPersistedRunSnapshotId.Should().BeNull();
        machine.CurrentState.Should().Be(RunState.Combat);
    }

    // ACC:T35.3
    [Fact]
    public void ShouldKeepExistingPersistenceMarkersUnchanged_WhenLaterPayloadIsInvalid()
    {
        var machine = BuildMachineAtCombatState();
        var validPayload = BuildVictorySettlementPayload(isComplete: true);
        CombatResolutionCommandPayload.TryParse(validPayload, out var parsed).Should().BeTrue();
        parsed.Should().NotBeNull();

        machine.TryProcessCommand(
            CreateCommand("cmd-t35-seed-valid", "complete_combat", validPayload),
            out _).Should().BeTrue();
        machine.LastPersistedRunSnapshotId.Should().Be(parsed!.RewardHandoff!.RunSnapshotId);
        machine.LastPersistenceSourceState.Should().Be(RunState.Combat);

        machine.TryProcessCommand(CreateCommand("cmd-t35-claim", "claim_reward"), out _).Should().BeTrue();
        machine.TryProcessCommand(CreateCommand("cmd-t35-start-again", "start_combat"), out _).Should().BeTrue();
        machine.CurrentState.Should().Be(RunState.Combat);

        var invalidPayload = JsonSerializer.Serialize(new
        {
            settlement_completed = true,
            death_triggers_resolved = true,
            reward_offer_presented = true,
            run_state_persisted = true,
            settlement_stages = new[] { "death_triggers_resolved", "reward_offer_presented", "run_state_persisted" },
            reward_handoff = new
            {
                reward_context_id = "reward.task35.invalid-overwrite",
                offer_ids = Array.Empty<string>(),
                run_snapshot_id = "snapshot.task35.invalid-overwrite"
            }
        });

        var accepted = machine.TryProcessCommand(
            CreateCommand("cmd-t35-invalid-after-seed", "complete_combat", invalidPayload),
            out var transition);

        accepted.Should().BeFalse();
        transition.Reason.Should().Be("invalid_command_no_transition");
        machine.LastPersistedRunSnapshotId.Should().Be(parsed.RewardHandoff!.RunSnapshotId);
        machine.LastPersistenceSourceState.Should().Be(RunState.Combat);
        machine.CurrentState.Should().Be(RunState.Combat);
    }

    // ACC:T35.3
    [Fact]
    public void ShouldExposeTask35RefsInOverlayAndTaskView_WhenCheckingTraceability()
    {
        var repoRoot = ResolveRepoRoot();
        var overlayPath = Path.Combine(repoRoot, OverlayIndexPath.Replace('/', Path.DirectorySeparatorChar));
        var taskPath = Path.Combine(repoRoot, TasksGameplayPath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(overlayPath).Should().BeTrue();
        File.Exists(taskPath).Should().BeTrue();

        var overlayContent = File.ReadAllText(overlayPath);
        overlayContent.Should().Contain("Test-Refs:");
        overlayContent.Should().Contain(ThisTaskTestRef);
        overlayContent.Should().Contain("Game.Core.Tests/Services/CombatServiceTests.cs");

        using var taskDoc = JsonDocument.Parse(File.ReadAllText(taskPath));
        var task35 = taskDoc.RootElement
            .EnumerateArray()
            .First(node => node.TryGetProperty("taskmaster_id", out var idNode) && idNode.GetInt32() == 35);
        var testRefs = task35.GetProperty("test_refs")
            .EnumerateArray()
            .Select(node => node.GetString())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .ToArray();
        testRefs.Should().Contain(ThisTaskTestRef);
        testRefs.Should().Contain("Game.Core.Tests/Services/CombatServiceTests.cs");
    }

    private static RunStateMachine BuildMachineAtCombatState()
    {
        var machine = new RunStateMachine();
        machine.TryProcessCommand(CreateCommand("cmd-enter", "enter_node"), out _).Should().BeTrue();
        machine.TryProcessCommand(CreateCommand("cmd-start", "start_combat"), out _).Should().BeTrue();
        machine.CurrentState.Should().Be(RunState.Combat);
        return machine;
    }

    private static RunCommand CreateCommand(string commandId, string commandType, string? payloadJson = null)
    {
        var resolvedPayload = payloadJson
            ?? (commandType == "complete_combat" ? BuildVictorySettlementPayload(isComplete: true) : "{}");
        return new RunCommand(
            CommandId: commandId,
            CommandType: commandType,
            Issuer: "task35-acceptance-tests",
            PayloadJson: resolvedPayload,
            IssuedAt: new DateTimeOffset(2026, 4, 19, 0, 0, 0, TimeSpan.Zero));
    }

    private static string BuildVictorySettlementPayload(bool isComplete)
    {
        var pipelineInput = new PlayCardPipelineInput(
            DifficultyId: 10,
            CardsPlayedThisTurn: 2,
            OverplayTriggerN: 3,
            OverplayTaxPerCard: 2,
            BaseCardCost: 1,
            EnergyBefore: 10,
            BaseDamage: 12,
            Strength: 2,
            WeakMultiplier: 1.0,
            VulnerableMultiplier: 1.0,
            IsFixedDamage: false,
            CombatantId: "task35-acceptance-combatant",
            StableId: "task35-acceptance-stable",
            FailAtStep: null);
        var pipelineResult = new CombatService().ExecutePlayCardPipeline(pipelineInput);
        var settlementStages = isComplete
            ? new[] { "death_triggers_resolved", "reward_offer_presented", "run_state_persisted" }
            : new[] { "death_triggers_resolved", "reward_offer_presented" };

        var payload = new
        {
            settlement_completed = isComplete && pipelineResult.Success,
            death_triggers_resolved = pipelineResult.StateAfter.DeathCheckCompleted,
            reward_offer_presented = true,
            run_state_persisted = isComplete,
            settlement_stages = settlementStages,
            reward_handoff = isComplete
                ? new
                {
                    reward_context_id = "reward.task35.acceptance",
                    offer_ids = new[] { "offer.task35.a", "offer.task35.b", "offer.task35.c" },
                    run_snapshot_id = "snapshot.task35.acceptance"
                }
                : null
        };
        return JsonSerializer.Serialize(payload);
    }

    private static string ResolveRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }
}
