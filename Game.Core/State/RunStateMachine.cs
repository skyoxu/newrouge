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
    public string? LastPersistedRunSnapshotId { get; private set; }
    public RunState? LastPersistenceSourceState { get; private set; }

    public IReadOnlyList<RunTransition> Transitions => _transitions;

    public bool TryProcessCommand(RunCommand command, out RunTransition transition)
    {
        if (command.CommandType == "complete_combat" && CurrentState == RunState.Combat)
        {
            if (!TryPersistCombatResolutionMarker(CurrentState, command))
            {
                transition = Handle(CurrentState, command);
                return false;
            }
        }

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
        var nextState = ResolveNextState(currentState, command);
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

    private static RunState ResolveNextState(RunState currentState, RunCommand command)
    {
        return command.CommandType switch
        {
            "enter_node" when currentState == RunState.MainMenu => RunState.NodePreEnter,
            "start_combat" when currentState == RunState.NodePreEnter => RunState.Combat,
            "complete_combat" when currentState == RunState.Combat && IsVictorySettlementCompleted(command) => RunState.Reward,
            "resolve_combat_defeat" when currentState == RunState.Combat => RunState.GameOver,
            "claim_reward" when currentState == RunState.Reward => RunState.NodePreEnter,
            "open_shop" when currentState == RunState.NodePreEnter => RunState.Shop,
            "leave_shop" when currentState == RunState.Shop => RunState.NodePreEnter,
            "open_rest" when currentState == RunState.NodePreEnter => RunState.Rest,
            "leave_rest" when currentState == RunState.Rest => RunState.NodePreEnter,
            "open_event" when currentState == RunState.NodePreEnter => RunState.Event,
            "resolve_event" when currentState == RunState.Event => RunState.NodePreEnter,
            "end_run" when currentState != RunState.GameOver => RunState.GameOver,
            "return_to_menu" when currentState == RunState.GameOver => RunState.MainMenu,
            _ => currentState,
        };
    }

    private static bool IsVictorySettlementCompleted(RunCommand command)
    {
        if (!CombatResolutionCommandPayload.TryParse(command.PayloadJson, out var payload) || payload is null)
        {
            return false;
        }

        return payload.MeetsVictoryTransitionRequirements();
    }

    private bool TryPersistCombatResolutionMarker(RunState sourceState, RunCommand command)
    {
        if (!CombatResolutionCommandPayload.TryParse(command.PayloadJson, out var payload) || payload is null)
        {
            return false;
        }

        if (!payload.MeetsVictoryTransitionRequirements())
        {
            return false;
        }

        LastPersistedRunSnapshotId = payload.RewardHandoff!.RunSnapshotId;
        LastPersistenceSourceState = sourceState;
        return true;
    }
}
