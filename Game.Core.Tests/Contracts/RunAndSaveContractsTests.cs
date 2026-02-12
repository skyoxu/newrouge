using System;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.Contracts.Run;
using Game.Core.Contracts.Save;
using Xunit;

namespace Game.Core.Tests.Contracts;

public class RunAndSaveContractsTests
{
    [Fact]
    public void RunTransition_and_command_follow_command_driven_model()
    {
        var command = new RunCommand(
            CommandId: "cmd-1",
            CommandType: "enter_node",
            Issuer: "player",
            PayloadJson: "{\"nodeId\":\"N-2\"}",
            IssuedAt: DateTimeOffset.UtcNow
        );

        var transition = new RunTransition(
            FromState: RunState.NodePreEnter,
            ToState: RunState.Combat,
            Reason: "node_type_combat",
            CorrelationId: command.CommandId,
            TransitionedAt: DateTimeOffset.UtcNow
        );

        transition.FromState.Should().Be(RunState.NodePreEnter);
        transition.ToState.Should().Be(RunState.Combat);
        transition.CorrelationId.Should().Be("cmd-1");
    }

    [Fact]
    public void Autosave_and_continue_metadata_keep_single_slot_context()
    {
        var autosave = new AutosaveSnapshot(
            RunId: "run-1",
            SavePointId: "reward-opened-floor-2",
            SchemaVersion: "1.0.0",
            StateJson: "{\"hp\":60}",
            SavedAt: DateTimeOffset.UtcNow
        );

        var metadata = new ContinueMetadata(
            RunId: autosave.RunId,
            DifficultyId: 7,
            Act: 1,
            NodeId: "N-2",
            IntegrityHash: "ABC123",
            UpdatedAt: DateTimeOffset.UtcNow
        );

        var difficulty = new DifficultyConfig(
            DifficultyId: 7,
            Name: "D7",
            BaseEnergyPerTurn: 3,
            BaseDrawPerTurn: 4,
            OverplayTriggerN: 12,
            EnableOverplayTax: false,
            IsUnlocked: true
        );

        metadata.RunId.Should().Be(autosave.RunId);
        difficulty.BaseEnergyPerTurn.Should().Be(3);
        difficulty.BaseDrawPerTurn.Should().Be(4);
    }
}
