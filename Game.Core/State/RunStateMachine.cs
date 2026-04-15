using System;
using System.Collections.Generic;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Run;

namespace Game.Core.State;

/// <summary>
/// Deterministic run state machine that only mutates state through command handling.
/// </summary>
public sealed class RunStateMachine : IRunCommandHandler
{
    private readonly List<RunTransition> _transitions = new();

    public RunStateMachine(RunState initialState = RunState.MainMenu)
    {
        CurrentState = initialState;
    }

    public RunState CurrentState { get; private set; }

    public IReadOnlyList<RunTransition> Transitions => _transitions;

    public bool TryProcessCommand(RunCommand command, out RunTransition transition)
    {
        transition = Handle(CurrentState, command);
        if (transition.ToState == CurrentState)
        {
            return false;
        }

        CurrentState = transition.ToState;
        _transitions.Add(transition);
        return true;
    }

    public RunTransition Handle(RunState currentState, RunCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        var nextState = ResolveNextState(currentState, command.CommandType);
        var reason = nextState == currentState ? "invalid_command_no_transition" : command.CommandType;
        return new RunTransition(
            FromState: currentState,
            ToState: nextState,
            Reason: reason,
            CorrelationId: command.CommandId,
            TransitionedAt: command.IssuedAt);
    }

    public void HandleNonCommandSignal(string signal)
    {
        // Non-command signals are intentionally ignored to preserve command-only transitions.
        _ = signal;
    }

    private static RunState ResolveNextState(RunState currentState, string commandType)
    {
        return commandType switch
        {
            "enter_node" when currentState == RunState.MainMenu => RunState.NodePreEnter,
            "start_combat" when currentState == RunState.NodePreEnter => RunState.Combat,
            "complete_combat" when currentState == RunState.Combat => RunState.Reward,
            "claim_reward" when currentState == RunState.Reward => RunState.NodePreEnter,
            "open_shop" when currentState == RunState.NodePreEnter => RunState.Shop,
            "leave_shop" when currentState == RunState.Shop => RunState.NodePreEnter,
            "open_rest" when currentState == RunState.NodePreEnter => RunState.Rest,
            "leave_rest" when currentState == RunState.Rest => RunState.NodePreEnter,
            "open_event" when currentState == RunState.NodePreEnter => RunState.Event,
            "resolve_event" when currentState == RunState.Event => RunState.NodePreEnter,
            "end_run" when currentState != RunState.GameOver => RunState.GameOver,
            _ => currentState,
        };
    }
}
