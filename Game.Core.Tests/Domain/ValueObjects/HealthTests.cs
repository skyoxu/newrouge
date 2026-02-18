using System;
using Game.Core.Domain.ValueObjects;
using Xunit;

namespace Game.Core.Tests.Domain.ValueObjects;

public class HealthTests
{
    [Fact]
    public void ShouldConstructorSetsCurrentEqualsMaxAndDisallowsNegative_WhenExecuted()
    {
        var h = new Health(100);
        Assert.Equal(100, h.Maximum);
        Assert.Equal(100, h.Current);
        Assert.True(h.IsAlive);
    }

    [Fact]
    public void ShouldTakeDamageClampsAtZeroAndIsImmutable_WhenExecuted()
    {
        var h = new Health(10);
        var h2 = h.TakeDamage(3);
        Assert.Equal(10, h.Current);
        Assert.Equal(7, h2.Current);

        var h3 = h2.TakeDamage(100);
        Assert.Equal(0, h3.Current);
        Assert.False(h3.IsAlive);
    }

    [Fact]
    public void ShouldTakeDamageNegativeThrows_WhenExecuted()
    {
        var h = new Health(10);
        Assert.Throws<ArgumentOutOfRangeException>(() => h.TakeDamage(-1));
    }
}
