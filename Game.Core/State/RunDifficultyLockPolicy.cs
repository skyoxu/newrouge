using System;

namespace Game.Core.State;

/// <summary>
/// Controls the mutable-before-run, read-only-during-run difficulty selection policy.
/// </summary>
public sealed class RunDifficultyLockPolicy
{
    public int SelectedDifficultyId { get; private set; }

    public bool IsLocked { get; private set; }

    public RunDifficultyLockPolicy(int initialDifficultyId = 1)
    {
        SelectedDifficultyId = Math.Clamp(initialDifficultyId, 1, 10);
    }

    public bool SelectDifficulty(int difficultyId)
    {
        var bounded = Math.Clamp(difficultyId, 1, 10);
        if (IsLocked && bounded != SelectedDifficultyId)
        {
            return false;
        }

        SelectedDifficultyId = bounded;
        return true;
    }

    public void Lock()
    {
        IsLocked = true;
    }
}
