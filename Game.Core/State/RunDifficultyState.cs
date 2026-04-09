using System;

namespace Game.Core.State;

public static class RunDifficultyState
{
    private static int _confirmedDifficulty = 1;

    public static int GetConfirmedDifficulty()
    {
        return _confirmedDifficulty;
    }

    public static void SetConfirmedDifficulty(int difficultyId)
    {
        _confirmedDifficulty = Math.Clamp(difficultyId, 1, 10);
    }
}
