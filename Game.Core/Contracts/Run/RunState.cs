namespace Game.Core.Contracts.Run;

/// <summary>
/// High-level run state for command-driven transitions.
/// </summary>
public enum RunState
{
    MainMenu = 1,
    NodePreEnter = 2,
    Combat = 3,
    Reward = 4,
    Shop = 5,
    Rest = 6,
    Event = 7,
    GameOver = 8,
}

