using System;
using Game.Core.State;
using Game.Core.Contracts.Run;
using Xunit;

namespace Game.Core.Tests.State;

public class GameStateMachineTests
{
    // ACC:T43.4
    [Fact]
    public void ShouldTransitionsFollowHappyPathAndFireEvents_WhenExecuted()
    {
        var fsm = new GameStateMachine();
        int calls = 0;
        fsm.OnTransition += (prev, next) => calls++;

        Assert.True(fsm.Start());
        Assert.True(fsm.Pause());
        Assert.True(fsm.Resume());
        Assert.True(fsm.End());

        Assert.Equal(GameFlowState.GameOver, fsm.State);
        Assert.True(calls >= 3);
    }

    // ACC:T43.6
    [Fact]
    public void ShouldInvalidTransitionsAreRejected_WhenExecuted()
    {
        var fsm = new GameStateMachine();
        Assert.False(fsm.Resume());
        Assert.True(fsm.End());
        Assert.False(fsm.End());
        Assert.False(fsm.Start());
    }

    // ACC:T43.7
    [Fact]
    public void ShouldRunStateMachineFollowDeterministicCommandOrder_WhenExecuted()
    {
        var machine = new RunStateMachine();
        var commands = new[]
        {
            CreateCommand("cmd-1", "enter_node"),
            CreateCommand("cmd-2", "start_combat"),
            CreateCommand("cmd-3", "complete_combat"),
            CreateCommand("cmd-4", "claim_reward"),
        };

        foreach (var command in commands)
        {
            Assert.True(machine.TryProcessCommand(command, out _));
        }

        Assert.Equal(RunState.NodePreEnter, machine.CurrentState);
        Assert.Collection(
            machine.Transitions,
            first => Assert.Equal(RunState.NodePreEnter, first.ToState),
            second => Assert.Equal(RunState.Combat, second.ToState),
            third => Assert.Equal(RunState.Reward, third.ToState),
            fourth => Assert.Equal(RunState.NodePreEnter, fourth.ToState));
    }

    // ACC:T43.5
    [Fact]
    public void ShouldRunStateMachineKeepState_WhenCommandIsInvalidForCurrentState()
    {
        var machine = new RunStateMachine();
        var accepted = machine.TryProcessCommand(CreateCommand("cmd-invalid", "complete_combat"), out var transition);

        Assert.False(accepted);
        Assert.Equal(RunState.MainMenu, machine.CurrentState);
        Assert.Empty(machine.Transitions);
        Assert.Equal("invalid_command_no_transition", transition.Reason);
    }

    private static RunCommand CreateCommand(string commandId, string commandType)
    {
        return new RunCommand(
            CommandId: commandId,
            CommandType: commandType,
            Issuer: "state-tests",
            PayloadJson: "{}",
            IssuedAt: new DateTimeOffset(2026, 4, 15, 10, 0, 0, TimeSpan.Zero));
    }
}
