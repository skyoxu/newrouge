using Game.Core.Domain;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public class ScoreServiceTests
{
    [Fact]
    public void ShouldComputeAddedScoreRespectsMultiplierAndDifficulty_WhenExecuted()
    {
        var svc = new ScoreService();
        var cfg = new GameConfig(
            MaxLevel: 50,
            InitialHealth: 100,
            ScoreMultiplier: 1.5,
            AutoSave: false,
            Difficulty: Difficulty.Medium
        );

        var added = svc.ComputeAddedScore(100, cfg);
        Assert.Equal(150, added); // 100 * 1.5 * 1.0

        cfg = cfg with { Difficulty = Difficulty.Hard };
        var hardAdded = svc.ComputeAddedScore(100, cfg);
        Assert.Equal(180, hardAdded); // 100 * 1.5 * 1.2
    }

    [Fact]
    public void ShouldComputeAddedScoreHandlesEasyUnknownAndNegativeBasePoints_WhenExecuted()
    {
        var svc = new ScoreService();
        var cfg = new GameConfig(50, 100, 1.0, false, Difficulty.Easy);

        var easyAdded = svc.ComputeAddedScore(100, cfg);
        Assert.Equal(90, easyAdded); // 100 * 1.0 * 0.9

        cfg = cfg with { Difficulty = (Difficulty)999 };
        var unknownDifficultyAdded = svc.ComputeAddedScore(10, cfg);
        Assert.Equal(10, unknownDifficultyAdded); // default multiplier 1.0

        var negativeBase = svc.ComputeAddedScore(-123, cfg);
        Assert.Equal(0, negativeBase);
    }

    [Fact]
    public void ShouldAddAccumulatesAndResetClearsScore_WhenExecuted()
    {
        var svc = new ScoreService();
        var cfg = new GameConfig(50, 100, 1.0, false, Difficulty.Medium);

        svc.Add(10, cfg);
        svc.Add(20, cfg);

        Assert.True(svc.Score > 0);

        var before = svc.Score;
        Assert.Equal(before, svc.Score);

        svc.Reset();
        Assert.Equal(0, svc.Score);
    }

    [Fact]
    public void ShouldAddWithNegativePointsDoesNotDecreaseScore_WhenExecuted()
    {
        var svc = new ScoreService();
        var cfg = new GameConfig(50, 100, 1.0, false, Difficulty.Medium);

        svc.Add(10, cfg);
        var before = svc.Score;

        svc.Add(-999, cfg);

        Assert.Equal(before, svc.Score);
    }
}

