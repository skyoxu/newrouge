using Game.Core.Contracts.Run;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Command-only run state progression handler.
/// </summary>
public interface IRunCommandHandler
{
    RunTransition Handle(RunState currentState, RunCommand command);
}

