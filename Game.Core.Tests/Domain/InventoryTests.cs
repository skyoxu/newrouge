using Game.Core.Domain;
using Xunit;

namespace Game.Core.Tests.Domain;

public class InventoryTests
{
    [Fact]
    public void ShouldAddAndRemoveRespectMaxStackAndCounts_WhenExecuted()
    {
        var inv = new Inventory();
        Assert.Equal(0, inv.CountItem("potion"));
        var added = inv.Add("potion", count: 120, maxStack: 99);
        Assert.Equal(99, added);
        Assert.True(inv.HasItem("potion", atLeast: 50));

        var removed = inv.Remove("potion", count: 60);
        Assert.Equal(60, removed);
        Assert.Equal(39, inv.CountItem("potion"));

        removed = inv.Remove("potion", count: 100);
        Assert.Equal(39, removed);
        Assert.Equal(0, inv.CountItem("potion"));
    }

    [Fact]
    public void ShouldAddReturnsZeroWhenCountIsNonPositiveOrStackIsFull_WhenExecuted()
    {
        var inv = new Inventory();

        Assert.Equal(0, inv.Add("ore", count: 0, maxStack: 99));
        Assert.Equal(0, inv.Add("ore", count: -3, maxStack: 99));

        Assert.Equal(2, inv.Add("ore", count: 2, maxStack: 2));
        Assert.Equal(0, inv.Add("ore", count: 1, maxStack: 2));
        Assert.Equal(2, inv.CountItem("ore"));
    }

    [Fact]
    public void ShouldRemoveReturnsZeroWhenCountIsNonPositiveOrItemMissing_WhenExecuted()
    {
        var inv = new Inventory();

        Assert.Equal(0, inv.Remove("missing", count: 1));
        Assert.Equal(0, inv.Remove("missing", count: 0));
        Assert.Equal(0, inv.Remove("missing", count: -2));

        inv.Add("key", count: 1);
        Assert.Equal(0, inv.Remove("key", count: 0));
        Assert.Equal(1, inv.CountItem("key"));
    }

    [Fact]
    public void ShouldHasItemUsesRequestedThreshold_WhenExecuted()
    {
        var inv = new Inventory();
        inv.Add("coin", count: 2);

        Assert.True(inv.HasItem("coin"));
        Assert.True(inv.HasItem("coin", atLeast: 2));
        Assert.False(inv.HasItem("coin", atLeast: 3));
        Assert.False(inv.HasItem("missing"));
    }
}

