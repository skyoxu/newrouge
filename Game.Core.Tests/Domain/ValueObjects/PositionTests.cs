using Game.Core.Domain.ValueObjects;
using Xunit;

namespace Game.Core.Tests.Domain.ValueObjects;

public class PositionTests
{
    [Fact]
    public void ShouldAddReturnsNewPositionAndKeepsImmutable_WhenExecuted()
    {
        var p = new Position(1, 2);
        var p2 = p.Add(3, 4);
        Assert.Equal(1, p.X);
        Assert.Equal(2, p.Y);
        Assert.Equal(4, p2.X);
        Assert.Equal(6, p2.Y);
        Assert.NotEqual(p, p2);
    }
}

