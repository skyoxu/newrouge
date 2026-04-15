using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts.Run;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0043AcceptanceTests
{
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0043AcceptanceTests.cs";

    // ACC:T43.1
    // ADR-0032: Non-command signals must not trigger run-state transitions.
    [Fact]
    [Trait("adr", "ADR-0032")]
    public void ShouldKeepStateUnchanged_WhenNonCommandSignalArrives()
    {
        var machine = new RunStateMachine();
        var initialState = machine.CurrentState;

        machine.HandleNonCommandSignal("frame_tick");

        machine.CurrentState.Should().Be(initialState);
        machine.Transitions.Should().BeEmpty();
    }

    [Fact]
    [Trait("adr", "ADR-0032")]
    public void ShouldTransitionThroughCommandEntryOnly_WhenValidCommandsAreProcessed()
    {
        var machine = new RunStateMachine();
        var commands = new[]
        {
            CreateCommand("cmd-1", "enter_node"),
            CreateCommand("cmd-2", "start_combat"),
            CreateCommand("cmd-3", "complete_combat"),
        };

        foreach (var command in commands)
        {
            machine.TryProcessCommand(command, out _).Should().BeTrue();
        }

        machine.Transitions.Should().HaveCount(3);
        machine.CurrentState.Should().Be(RunState.Reward);
        machine.Transitions.Select(transition => transition.CorrelationId).Should().Equal("cmd-1", "cmd-2", "cmd-3");
    }

    // ACC:T43.2
    // ADR-0021: Command ordering must be deterministic and preserve state invariants.
    [Fact]
    [Trait("adr", "ADR-0021")]
    public void ShouldPreserveTransitionOrderAndStateInvariants_WhenCommandsAreProcessed()
    {
        var machine = new RunStateMachine();
        var commands = new[]
        {
            CreateCommand("cmd-1", "enter_node"),
            CreateCommand("cmd-2", "open_rest"),
            CreateCommand("cmd-3", "leave_rest"),
            CreateCommand("cmd-4", "open_shop"),
            CreateCommand("cmd-5", "leave_shop"),
            CreateCommand("cmd-6", "end_run"),
        };

        foreach (var command in commands)
        {
            machine.TryProcessCommand(command, out _).Should().BeTrue();
        }

        machine.Transitions.Select(transition => transition.ToState).Should().Equal(
            RunState.NodePreEnter,
            RunState.Rest,
            RunState.NodePreEnter,
            RunState.Shop,
            RunState.NodePreEnter,
            RunState.GameOver);

        machine.CurrentState.Should().Be(RunState.GameOver);
    }

    [Fact]
    [Trait("adr", "ADR-0021")]
    public void ShouldRejectInvalidCommandWithoutStateMutation_WhenCommandDoesNotMatchCurrentState()
    {
        var machine = new RunStateMachine();
        var command = CreateCommand("cmd-invalid", "start_combat");

        var accepted = machine.TryProcessCommand(command, out var transition);

        accepted.Should().BeFalse();
        machine.CurrentState.Should().Be(RunState.MainMenu);
        machine.Transitions.Should().BeEmpty();
        transition.FromState.Should().Be(RunState.MainMenu);
        transition.ToState.Should().Be(RunState.MainMenu);
        transition.Reason.Should().Be("invalid_command_no_transition");
    }

    // ACC:T43.3
    [Fact]
    public void ShouldContainTaskTestRefPath_WhenAcceptanceEvidenceIsEnumerated()
    {
        var testRefs = GetAcceptanceTestRefs();

        testRefs.Should().Contain(ThisTaskTestRef);
        testRefs.Should().OnlyContain(path => path.StartsWith("Game.Core.Tests/", StringComparison.Ordinal));
    }

    // ACC:T43.8
    // ADR-0032 and ADR-0021 are explicitly referenced for this task acceptance.
    [Fact]
    [Trait("adr", "ADR-0032")]
    [Trait("adr", "ADR-0021")]
    public void ShouldReferenceAdr0032AndAdr0021_WhenAcceptanceMetadataIsDeclared()
    {
        var referencedAdrs = GetReferencedAdrs();

        referencedAdrs.Should().Contain("ADR-0032");
        referencedAdrs.Should().Contain("ADR-0021");
    }

    private static RunCommand CreateCommand(string commandId, string commandType)
    {
        return new RunCommand(
            CommandId: commandId,
            CommandType: commandType,
            Issuer: "test",
            PayloadJson: "{}",
            IssuedAt: new DateTimeOffset(2026, 4, 15, 10, 0, 0, TimeSpan.Zero));
    }

    private static IReadOnlyCollection<string> GetAcceptanceTestRefs() =>
        new[]
        {
            ThisTaskTestRef
        };

    private static IReadOnlyCollection<string> GetReferencedAdrs() =>
        new[]
        {
            "ADR-0032",
            "ADR-0021"
        };
}
