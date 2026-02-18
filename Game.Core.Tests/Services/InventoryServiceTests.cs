using FluentAssertions;
using Game.Core.Domain;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public class InventoryServiceTests
{
    [Fact]
    public void ShouldAddShouldReturnZeroWhenNewItemAndSlotCapacityReached_WhenExecuted()
    {
        var inventory = new Inventory();
        var service = new InventoryService(inventory, maxSlots: 1);

        service.Add("item-a", 1).Should().Be(1);
        service.Add("item-b", 1).Should().Be(0);
        service.CountDistinct().Should().Be(1);
    }

    [Fact]
    public void ShouldAddShouldStillWorkWhenExistingItemAndSlotCapacityReached_WhenExecuted()
    {
        var inventory = new Inventory();
        var service = new InventoryService(inventory, maxSlots: 1);

        service.Add("item-a", 1).Should().Be(1);
        service.Add("item-a", 3).Should().Be(3);
        service.CountItem("item-a").Should().Be(4);
    }

    [Fact]
    public void ShouldAddShouldRespectMaxStackCap_WhenExecuted()
    {
        var inventory = new Inventory();
        var service = new InventoryService(inventory, maxSlots: 2);

        service.Add("item-a", count: 150, maxStack: 99).Should().Be(99);
        service.CountItem("item-a").Should().Be(99);
    }

    [Fact]
    public void ShouldRemoveShouldClampToAvailableAndDeleteEmptyEntry_WhenExecuted()
    {
        var inventory = new Inventory();
        var service = new InventoryService(inventory, maxSlots: 2);

        service.Add("item-a", 2).Should().Be(2);
        service.Remove("item-a", 3).Should().Be(2);
        service.CountItem("item-a").Should().Be(0);
        service.HasItem("item-a").Should().BeFalse();
    }

    [Fact]
    public void ShouldCountAndHasItemShouldReflectCurrentInventoryState_WhenExecuted()
    {
        var inventory = new Inventory();
        var service = new InventoryService(inventory, maxSlots: 3);

        service.CountDistinct().Should().Be(0);
        service.HasItem("item-a").Should().BeFalse();

        service.Add("item-a", 2);
        service.CountDistinct().Should().Be(1);
        service.HasItem("item-a", atLeast: 2).Should().BeTrue();
        service.HasItem("item-a", atLeast: 3).Should().BeFalse();
    }
}
